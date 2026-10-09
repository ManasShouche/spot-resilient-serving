"""Planner trials: does the evacuation planner pick better than simple orders when not
everything fits before the deadline (budget ratio rho < 1)?

Earlier GPU runs had rho >> 1 (10 GB left in 6.6 s of a 120 s notice), so the planner
never had to choose. Here the notice is short (15 or 30 s) and the link to the memory
node is throttled, so only part of the resident session KV can leave in time.

Three steps:

1. `export` (where the AgentX trace is): simulate the 8B fleet on the real sessions and
   take node snapshots. From each snapshot, draw idle sessions at random until they fill
   what one g6e.2xlarge CPU tier holds. Each session keeps its real context length
   (capped at the model's 128k window), idle time and whether it really returns.
2. `run` (on the GPU node): for every snapshot, notice and policy, prefill fresh copies
   of the sessions, ask the plugin to flush before the deadline in that policy's order,
   and record which blocks were confirmed on the memory node by the deadline.
3. `score`: value of what each policy saved, judged against whether each session really
   returns (which no policy is told). Recompute uses the measured L40S prefill curve and
   restore the measured two-node rate, so saving a context that is cheaper to recompute
   than to restore is worth nothing.

Policies: `planner` (the plugin's own value-density order with recency-based reuse
estimates), `recent` (most recently used first), `largest` (longest context first),
`random`, and `oracle` (returning sessions only, longest first; an upper bound).

    python -m kvevac.planner_trials export --trace data/raw/agentx.jsonl --out trials.json
    python -m kvevac.planner_trials run --trials trials.json --tier /mnt/peer/t --out DIR
    python -m kvevac.planner_trials score DIR/planner_trials.json
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from kvevac.costmodel import recompute_s
from kvevac.profiles import GpuProfile

POLICIES = ("planner", "recent", "largest", "random", "oracle")
NOTICES_S = (10.0, 15.0, 30.0, 60.0)
LINKS_MBPS = (250.0, 1000.0)
"""Shaped egress to the memory node; unshaped NFS writes ran at 1.3-1.5 GB/s."""
KV_BYTES_PER_TOKEN = 131_072  # Llama-3.1-8B, bf16
MAX_CONTEXT = 120_000
"""Longest prefill we replay: the 128k window minus room for the wake-up requests."""
CAPACITY_TOKENS = 240_000
"""Session KV per trial: what a 36 GiB CPU tier holds (~294k tokens) minus margin."""
L40S_MEASURED = GpuProfile("l40s-measured", 16_011, 20_506, 46.7)
"""results/phase2/l40s-us-east-2-20261007/fit.json"""
RESTORE_BPS = 0.9e9
"""Two-node restore from the memory node, end to end (docs/phase3-results.md 2b)."""
WORDS_PER_TOKEN = 1 / 1.02
"""gpu_test's random-word prompts: 56,000 words came to 57,204 Llama-3 tokens."""
SETTLE_S = 12.0


# --------------------------------------------------------------------------- export
def export(trace: Path, out: Path, *, snapshots: int, seed: int, sessions: int) -> dict:
    from kvevac.characterize import ARRIVAL_WINDOW_S, SCENARIOS, WARMUP_S
    from kvevac.profiles import GPUS, LINKS, MODELS
    from kvevac.sim import Policy, Simulation
    from kvevac.workload import load_agentx_jsonl, resample_sessions

    scenario = SCENARIOS[0]  # 8B, 4M-token cache: the node the characterization uses
    real = load_agentx_jsonl(trace, arrival_window_s=ARRIVAL_WINDOW_S)
    workload = resample_sessions(real, sessions, arrival_window_s=ARRIVAL_WINDOW_S,
                                 seed=seed)
    sim = Simulation(workload, [], policy=Policy.RECOMPUTE, fleet=scenario.fleet,
                     model=MODELS[scenario.model], gpu=GPUS[scenario.gpu],
                     link=LINKS["25gbe"], snapshot_every_s=300.0,
                     snapshot_until_s=ARRIVAL_WINDOW_S, snapshot_sessions=True)
    rows = [r for r in sim.run().at_risk
            if r["t_s"] >= WARMUP_S and sum(1 for s in r["detail"] if not s["in_flight"]) >= 4]
    rng = random.Random(seed)
    picked = rng.sample(rows, min(snapshots, len(rows)))
    trials = []
    for index, row in enumerate(picked):
        idle = [s for s in row["detail"] if not s["in_flight"]]
        rng.shuffle(idle)
        chosen, used = [], 0
        for s in idle:
            tokens = min(int(s["tokens"]), MAX_CONTEXT)
            if tokens < 1_000 or used + tokens > CAPACITY_TOKENS:
                continue
            chosen.append({"tokens": tokens, "idle_s": s["idle_s"],
                           "returns": bool(s["returns"]),
                           "capped": int(s["tokens"]) > MAX_CONTEXT})
            used += tokens
        trials.append({"snapshot": index, "t_s": row["t_s"], "node": row["node"],
                       "node_sessions": row["sessions"], "sessions": chosen})
    result = {"trace": trace.name, "seed": seed, "workload_sessions": sessions,
              "capacity_tokens": CAPACITY_TOKENS, "max_context": MAX_CONTEXT,
              "trials": trials}
    out.write_text(json.dumps(result, indent=1))
    return result


# -------------------------------------------------------------------------- orders
def baseline_order(policy: str, sessions: dict[str, dict], seed: str) -> list[str] | None:
    """Session priority for a baseline; None lets the plugin's planner decide."""
    ids = list(sessions)
    if policy == "planner":
        return None
    if policy == "recent":
        return sorted(ids, key=lambda s: sessions[s]["idle_s"])
    if policy == "largest":
        return sorted(ids, key=lambda s: -sessions[s]["tokens"])
    if policy == "random":
        random.Random(seed).shuffle(ids)
        return ids
    if policy == "oracle":
        back = sorted((s for s in ids if sessions[s]["returns"]),
                      key=lambda s: -sessions[s]["tokens"])
        return back + [s for s in ids if s not in back]
    raise ValueError(policy)


def saved_tokens(report: dict, deadline: float, tokens_per_key: float) -> dict[str, int]:
    """Prefix tokens per session confirmed on the tier by the deadline. Store jobs are
    submitted in priority order; this assumes they are confirmed in that order."""
    confirmed = sum(n for t, n in report.get("jobs_done", []) if t <= deadline)
    out: dict[str, int] = {}
    for session, keys in report.get("segments", []):
        take = min(keys, confirmed)
        out[session] = out.get(session, 0) + int(take * tokens_per_key)
        confirmed -= take
    return out


# ------------------------------------------------------------------------------ run
def throttle(iface: str, mbytes_per_s: float | None) -> None:
    """Shape the GPU node's egress (the only big traffic is NFS writes to the memory
    node). None removes the shaper."""
    subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"], capture_output=True)
    if mbytes_per_s:
        rate = f"{int(mbytes_per_s * 8)}mbit"
        subprocess.run(["tc", "qdisc", "add", "dev", iface, "root", "tbf", "rate", rate,
                        "burst", "32mb", "latency", "400ms"], check=True)


def run(args: argparse.Namespace) -> None:
    from kvevac.vllm_plugin.gpu_test import Server, log, write_bandwidth

    spec = json.loads(args.trials.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "planner_trials.json"
    tier, control = args.tier, args.out / "flush.json"
    tier.mkdir(parents=True, exist_ok=True)
    result = {"spec": spec, "notices_s": args.notices, "links_MBps": args.links,
              "link_GBps": {}, "snapshots": {}, "trials": []}
    stop_at = time.time() + args.max_minutes * 60
    rates = {}
    for link in args.links:  # measure what each shaper setting really delivers
        throttle(args.iface, link)
        rates[link] = write_bandwidth(tier, gb=2)
        result["link_GBps"][str(link)] = round(rates[link] / 1e9, 3)
        log(f"link {link} MB/s shaped: {rates[link] / 1e9:.3f} GB/s to the tier")
    extra = {"flush_batch_keys": 64, "restore_bytes_per_s": RESTORE_BPS,
             "prefill_tokens_per_s": L40S_MEASURED.prefill_tokens_per_s,
             "attention_knee_tokens": L40S_MEASURED.attention_knee_tokens}
    throttle(args.iface, None)
    server = Server("P", 8001, args, tier, "deferred", control, rates[args.links[0]],
                    extra=extra, max_model_len=131_072)
    seq = 0
    try:
        for trial in spec["trials"][:args.max_snapshots]:
            if time.time() > stop_at:
                log("time budget used up; stopping before the next snapshot")
                break
            throttle(args.iface, None)
            sessions = prefill(trial, args, log)
            result["snapshots"][str(trial["snapshot"])] = sessions
            resident = sum(s["prompt_tokens"] or s["tokens"] for s in sessions.values()) \
                * KV_BYTES_PER_TOKEN
            for link in args.links:
                if time.time() > stop_at:
                    break
                throttle(args.iface, link)
                for notice in args.notices:
                    # Everything fits: the order cannot matter, so one flush suffices.
                    fits = (notice - 2) * rates[link] >= 1.1 * resident
                    policies = ["planner"] if fits else list(POLICIES)
                    random.Random(f"{trial['snapshot']}-{link}-{notice}").shuffle(policies)
                    for policy in policies:
                        seq += 1
                        row = flush_trial(trial, sessions, link, rates[link], notice,
                                          policy, seq, tier, control, args, log)
                        result["trials"].append(row)
                        out_path.write_text(json.dumps(result, indent=1))
                        if server.proc.poll() is not None:
                            raise RuntimeError("vLLM died; see its log")
    finally:
        throttle(args.iface, None)
        server.kill()
        out_path.write_text(json.dumps(result, indent=1))
    log(json.dumps(score(result)["paired"])[:900])


def prefill(trial: dict, args: argparse.Namespace, log) -> dict[str, dict]:
    """Make the snapshot's sessions resident (once; every flush below reuses them)."""
    from kvevac.vllm_plugin.gpu_test import complete, text

    prefix = f"s{trial['snapshot']}"
    sessions = {f"{prefix}-{i}": dict(s) for i, s in enumerate(trial["sessions"])}
    for sid, s in sessions.items():
        words = max(1, int(s["tokens"] * WORDS_PER_TOKEN))
        reply = complete(8001, args.model, text(sid, words), sid, 1)
        s["prompt_tokens"] = reply["prompt_tokens"]
        s["prefill_s"] = reply["ttft_s"]
    log(f"snapshot {trial['snapshot']}: {len(sessions)} sessions, "
        f"{sum(s['prompt_tokens'] or 0 for s in sessions.values())} tokens resident")
    time.sleep(SETTLE_S)  # GPU -> CPU-tier stores land
    return sessions


def flush_trial(trial, sessions, link, rate, notice, policy, seq, tier, control, args,
                log) -> dict:
    from kvevac.vllm_plugin.core import FlushRequest, write_flush_request
    from kvevac.vllm_plugin.gpu_test import complete

    for child in tier.iterdir():  # what the previous flush shipped
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    order = baseline_order(policy, sessions, f"{trial['snapshot']}-{link}-{notice}")
    deadline = time.time() + notice
    write_flush_request(control, FlushRequest(
        seq=seq, deadline_unix=deadline, sessions=order, only=list(sessions),
        idle_s={sid: s["idle_s"] for sid, s in sessions.items()},
        tier_bytes_per_s=rate, reset=True))
    status = control.with_suffix(control.suffix + ".status")
    report = None
    while True:  # wake requests keep the scheduler stepping so it polls the control file
        complete(8001, args.model, "wake", "wake", 1)
        try:
            report = json.loads(status.read_text())
        except (OSError, ValueError):
            report = None
        if report and report.get("seq") != seq:
            report = None
        finished = report and report.get("finished_unix")
        if time.time() > deadline + 60 or (finished and time.time() > deadline):
            break
        time.sleep(0.5)
    row = {"snapshot": trial["snapshot"], "link_MBps": link, "notice_s": notice,
           "policy": policy, "seq": seq, "deadline_unix": round(deadline, 3)}
    if report and report.get("keys_submitted"):
        per_key = report["bytes_submitted"] / report["keys_submitted"] / KV_BYTES_PER_TOKEN
        row["saved_tokens"] = saved_tokens(report, deadline, per_key)
    if report:  # keep the result file small: it comes back over the serial console
        row["report"] = {k: report.get(k) for k in (
            "started_unix", "finished_unix", "keys_submitted", "bytes_submitted",
            "keys_confirmed", "projected_finish_unix", "sessions_planned", "segments")}
        row["report"]["keys_on_time"] = sum(n for t, n in report.get("jobs_done", [])
                                            if t <= deadline)
    log(f"flush {seq} snap {trial['snapshot']} {link} MB/s W={notice:.0f} {policy}: "
        f"{sum(row.get('saved_tokens', {}).values())} tokens saved")
    return row


def preview(spec: dict, rates_GBps: dict[str, float]) -> dict:
    """Offline prediction of the whole sweep: every flush ships exactly its planned
    budget on time. The GPU run measures what really arrives by the deadline."""
    from kvevac.vllm_plugin.core import FlushParams, FlushRequest, SessionIndex, plan_flush

    block = 256
    params = FlushParams(block_bytes=block * KV_BYTES_PER_TOKEN, block_tokens=block,
                         tier_bytes_per_s=1e9, tier_setup_s=0.3, gpu=L40S_MEASURED,
                         restore_bytes_per_s=RESTORE_BPS)
    result = {"spec": spec, "link_GBps": rates_GBps, "snapshots": {}, "trials": []}
    seq = 0
    for trial in spec["trials"]:
        prefix = f"s{trial['snapshot']}"
        sessions = {f"{prefix}-{i}": dict(s) for i, s in enumerate(trial["sessions"])}
        result["snapshots"][str(trial["snapshot"])] = sessions
        index = SessionIndex()
        for sid, s in sessions.items():
            for i in range(0, s["tokens"], block):
                index.record(sid, f"{sid}-{i}", i, 0.0)
        for link, rate in rates_GBps.items():
            for notice in NOTICES_S:
                for policy in POLICIES:
                    seq += 1
                    order = baseline_order(policy, sessions, f"{prefix}-{link}-{notice}")
                    req = FlushRequest(seq, 1000.0 + notice, order, only=list(sessions),
                                       idle_s={k: s["idle_s"] for k, s in sessions.items()},
                                       tier_bytes_per_s=rate * 1e9)
                    flush, _ = plan_flush(index, req, params, now_unix=1000.0)
                    saved: dict[str, int] = {}
                    for sid in flush.key_sessions:
                        saved[sid] = saved.get(sid, 0) + block
                    result["trials"].append({
                        "snapshot": trial["snapshot"], "link_MBps": float(link),
                        "notice_s": notice, "policy": policy, "deadline_unix": 0,
                        "saved_tokens": saved,
                        "report": {"keys_submitted": len(flush.keys), "keys_on_time":
                                   len(flush.keys)}})
    return result


# ---------------------------------------------------------------------------- score
def session_value_s(tokens: int) -> float:
    """Recompute seconds a restored prefix of `tokens` avoids (0 if restore is slower)."""
    if tokens <= 0:
        return 0.0
    return max(0.0, recompute_s(tokens, L40S_MEASURED)
               - tokens * KV_BYTES_PER_TOKEN / RESTORE_BPS)


def score(result: dict) -> dict:
    rows = []
    for t in result["trials"]:
        saved = t.get("saved_tokens", {})
        sessions = result["snapshots"][str(t["snapshot"])]
        real = {sid: s.get("prompt_tokens") or s["tokens"] for sid, s in sessions.items()}
        back = [sid for sid, s in sessions.items() if s["returns"]]
        resident = sum(real.values()) * KV_BYTES_PER_TOKEN
        possible = sum(session_value_s(real[sid]) for sid in back)
        value = sum(session_value_s(min(saved.get(sid, 0), real[sid])) for sid in back)
        report = t.get("report") or {}
        ontime = report.get("keys_on_time", 0)
        rate = result.get("link_GBps", {}).get(str(t.get("link_MBps")))
        rows.append({
            "snapshot": t["snapshot"], "link_MBps": t.get("link_MBps"),
            "notice_s": t["notice_s"], "policy": t["policy"],
            "rho": round((t["notice_s"] - 2) * rate * 1e9 / resident, 3) if rate else None,
            "saved_GB": round(sum(saved.values()) * KV_BYTES_PER_TOKEN / 1e9, 2),
            "returning_GB_saved": round(sum(min(saved.get(s, 0), real[s]) for s in back)
                                        * KV_BYTES_PER_TOKEN / 1e9, 2),
            "value_s": round(value, 2), "possible_s": round(possible, 2),
            "on_time": round(ontime / report["keys_submitted"], 3)
            if report.get("keys_submitted") else None})
    cells = sorted({(r["link_MBps"], r["notice_s"]) for r in rows})
    summary, paired = {}, {}
    for link, notice in cells:
        cell = [r for r in rows if r["link_MBps"] == link and r["notice_s"] == notice]
        name = f"{link:.0f}MB/s W={notice:.0f}s"
        rhos = [r["rho"] for r in cell if r["rho"] is not None]
        summary[name] = {"rho_mean": round(statistics.mean(rhos), 3) if rhos else None}
        for policy in POLICIES:
            vals = [r["value_s"] for r in cell if r["policy"] == policy]
            if vals:
                summary[name][policy] = _dist(vals)
        # Paired by snapshot: same sessions, same link and notice.
        for other in ("recent", "largest", "random"):
            diffs = []
            for snap in sorted({r["snapshot"] for r in cell}):
                mine = [r["value_s"] for r in cell
                        if r["snapshot"] == snap and r["policy"] == "planner"]
                theirs = [r["value_s"] for r in cell
                          if r["snapshot"] == snap and r["policy"] == other]
                if mine and theirs:
                    diffs.append(mine[0] - theirs[0])
            if diffs:
                paired[f"{name} planner-{other}"] = {
                    **_dist(diffs), "planner_ahead": sum(d > 0.005 for d in diffs),
                    "behind": sum(d < -0.005 for d in diffs)}
    return {"rows": rows, "summary": summary, "paired": paired}


def _dist(values: list[float]) -> dict:
    """Mean and a 95% t-interval half-width over snapshots."""
    n = len(values)
    mean = statistics.mean(values)
    if n < 2:
        return {"n": n, "mean": round(mean, 2), "ci95": None}
    t95 = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57, 7: 2.45, 8: 2.36, 9: 2.31,
           10: 2.26, 11: 2.23, 12: 2.20}.get(n, 2.0)
    return {"n": n, "mean": round(mean, 2),
            "ci95": round(t95 * statistics.stdev(values) / n ** 0.5, 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export")
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--snapshots", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--sessions", type=int, default=1600)
    p = sub.add_parser("run")
    p.add_argument("--trials", type=Path, required=True)
    p.add_argument("--tier", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--cpu-gb", type=float, default=36.0)
    p.add_argument("--max-snapshots", type=int, default=10)
    p.add_argument("--notices", type=float, nargs="+", default=list(NOTICES_S))
    p.add_argument("--links", type=float, nargs="+", default=list(LINKS_MBPS),
                   help="shaped egress rates to sweep, MB/s")
    p.add_argument("--iface", required=True, help="NIC that carries the NFS traffic")
    p.add_argument("--max-minutes", type=float, default=300.0,
                   help="start nothing new after this long (results must still upload)")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--logs", type=Path, default=Path("."))
    p = sub.add_parser("score")
    p.add_argument("result", type=Path)
    p = sub.add_parser("preview", help="predict the sweep offline from trials.json")
    p.add_argument("trials", type=Path)
    args = parser.parse_args()
    if args.cmd == "export":
        spec = export(args.trace, args.out, snapshots=args.snapshots, seed=args.seed,
                      sessions=args.sessions)
        for t in spec["trials"]:
            back = sum(s["returns"] for s in t["sessions"])
            print(f"snapshot {t['snapshot']}: {len(t['sessions'])} sessions, "
                  f"{sum(s['tokens'] for s in t['sessions'])} tokens, {back} return")
    elif args.cmd == "run":
        run(args)
    elif args.cmd == "preview":
        rates = {f"{link:.1f}": link / 1000 for link in LINKS_MBPS}
        scored = score(preview(json.loads(args.trials.read_text()), rates))
        print(json.dumps({"summary": scored["summary"], "paired": scored["paired"]},
                         indent=1))
    else:
        scored = score(json.loads(args.result.read_text()))
        print(json.dumps({"summary": scored["summary"], "paired": scored["paired"]},
                         indent=1))


if __name__ == "__main__":
    main()
