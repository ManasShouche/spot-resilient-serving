"""Which idle sessions will come back? A learned P(reuse) for the evacuation planner.

The planner sweep (docs/phase3-results.md §2e) found the planner's ordering no better
than simple orders, while an oracle that knows which sessions return saved 1.5-2x
more. The planner's P(reuse) is a recency curve fitted to published gap quantiles
(kvevac.reuse). This module asks whether a model over each session's own history does
better, and how much of the oracle gap that closes.

1. Dataset: run the same simulation the sweep's snapshots come from (the 8B node on the
   real AgentX sessions) and record every idle session at every snapshot, with features
   from its history up to that moment and the label "sends another turn".
2. Cross-fitting by source session: AgentX has 393 real sessions, resampled into the
   workload. Sessions are split into K folds by their *source* session, and every
   prediction comes from a model that never saw that source session. Without this,
   resampled copies of the same session leak between train and test.
3. Classifier metrics (AUC, Brier, log loss) for: the recency curve the planner uses,
   logistic regression, and gradient-boosted trees.
4. Planner value: offline sweep previews (kvevac.planner_trials.preview, which matched
   the L40S hardware run at 250 MB/s) with the planner fed the recency estimate, the
   learned estimate, or the oracle answer, on the hardware sweep's 14 snapshots and on
   a larger set.

    python -m kvevac.returnpred --trace data/raw/agentx.jsonl --out results/returnpred
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

from kvevac.reuse import recency_reuse_prob
from kvevac.workload import Session

FEATURES = ("log_idle", "turns_done", "log_age", "log_tokens", "log_last_gap",
            "log_mean_gap5", "log_max_gap", "idle_over_median_gap", "frac_long_gaps",
            "log_last_out", "growth_frac", "compactions", "recency_p")
LONG_GAP_S = 60.0


def features(session: Session, turns_done: int, idle_s: float, age_s: float,
             tokens: int) -> dict[str, float]:
    """What the server knows about an idle session: its own history so far."""
    done = session.turns[:max(1, turns_done)]
    offsets = [t.offset_s for t in done]
    gaps = [b - a for a, b in zip(offsets, offsets[1:], strict=False)] or [0.0]
    inputs = [t.input_tokens for t in done]
    median_gap = statistics.median(gaps) if gaps else 0.0
    growth = (inputs[-1] - inputs[-2]) / max(1, inputs[-2]) if len(inputs) > 1 else 0.0
    return {
        "log_idle": math.log1p(max(0.0, idle_s)),
        "turns_done": float(turns_done),
        "log_age": math.log1p(max(0.0, age_s)),
        "log_tokens": math.log1p(tokens),
        "log_last_gap": math.log1p(gaps[-1]),
        "log_mean_gap5": math.log1p(statistics.mean(gaps[-5:])),
        "log_max_gap": math.log1p(max(gaps)),
        "idle_over_median_gap": idle_s / max(1.0, median_gap),
        "frac_long_gaps": sum(g > LONG_GAP_S for g in gaps) / len(gaps),
        "log_last_out": math.log1p(done[-1].output_tokens),
        "growth_frac": max(-1.0, min(5.0, growth)),
        "compactions": float(sum(b < a * 0.5 for a, b in zip(inputs, inputs[1:],
                                                             strict=False))),
        "recency_p": recency_reuse_prob(idle_s),
    }


def source_of(session_id: str) -> str:
    """Resampled ids are '<source id[:12]>-<index>'; group by the source session."""
    return session_id.rsplit("-", 1)[0]


# --------------------------------------------------------------------------- dataset
def simulate(trace: Path, *, sessions: int, seed: int):
    """The sweep's simulation (kvevac.planner_trials.export), with per-session detail."""
    from kvevac.characterize import ARRIVAL_WINDOW_S, SCENARIOS, WARMUP_S
    from kvevac.profiles import GPUS, LINKS, MODELS
    from kvevac.sim import Policy, Simulation
    from kvevac.workload import load_agentx_jsonl, resample_sessions

    scenario = SCENARIOS[0]
    real = load_agentx_jsonl(trace, arrival_window_s=ARRIVAL_WINDOW_S)
    workload = resample_sessions(real, sessions, arrival_window_s=ARRIVAL_WINDOW_S,
                                 seed=seed)
    sim = Simulation(workload, [], policy=Policy.RECOMPUTE, fleet=scenario.fleet,
                     model=MODELS[scenario.model], gpu=GPUS[scenario.gpu],
                     link=LINKS["25gbe"], snapshot_every_s=300.0,
                     snapshot_until_s=ARRIVAL_WINDOW_S, snapshot_sessions=True)
    rows = [r for r in sim.run().at_risk if r["t_s"] >= WARMUP_S]
    return {s.id: s for s in workload}, rows


def dataset(by_id: dict[str, Session], rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        for s in row["detail"]:
            if s["in_flight"]:
                continue
            feats = features(by_id[s["id"]], s["turns_done"], s["idle_s"], s["age_s"],
                             int(s["tokens"]))
            out.append({"id": s["id"], "group": source_of(s["id"]), "t_s": row["t_s"],
                        "node": row["node"], "tokens": int(s["tokens"]),
                        "idle_s": s["idle_s"], "returns": bool(s["returns"]), **feats})
    return out


# ----------------------------------------------------------------------- cross-fit
def cross_fit(data: list[dict], *, folds: int, seed: int) -> dict[str, list[float]]:
    """Out-of-fold P(returns) for every row, per model, folds split by source session."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    groups = sorted({r["group"] for r in data})
    random.Random(seed).shuffle(groups)
    fold_of = {g: i % folds for i, g in enumerate(groups)}
    X = np.array([[r[f] for f in FEATURES] for r in data])
    y = np.array([r["returns"] for r in data], dtype=int)
    fold = np.array([fold_of[r["group"]] for r in data])
    preds = {"recency": [r["recency_p"] for r in data],
             "logistic": [0.0] * len(data), "boosted": [0.0] * len(data)}
    for k in range(folds):
        train, test = fold != k, fold == k
        models = {
            "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
            "boosted": HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                      max_leaf_nodes=15,
                                                      random_state=seed),
        }
        for name, model in models.items():
            model.fit(X[train], y[train])
            p = model.predict_proba(X[test])[:, 1]
            for i, v in zip(np.flatnonzero(test), p, strict=True):
                preds[name][i] = float(v)
    return preds


def classifier_metrics(data: list[dict], preds: dict[str, list[float]]) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    y = [int(r["returns"]) for r in data]
    base = sum(y) / len(y)
    out = {"rows": len(y), "positive_rate": round(base, 3),
           "constant": {"brier": round(brier_score_loss(y, [base] * len(y)), 4),
                        "log_loss": round(log_loss(y, [base] * len(y)), 4), "auc": 0.5}}
    for name, p in preds.items():
        clipped = [min(1 - 1e-6, max(1e-6, v)) for v in p]
        out[name] = {"auc": round(roc_auc_score(y, p), 4),
                     "brier": round(brier_score_loss(y, clipped), 4),
                     "log_loss": round(log_loss(y, clipped), 4)}
    return out


# ------------------------------------------------------------------- planner value
def planner_value(trials: list[dict], probs: dict[str, dict[str, float]]) -> dict:
    """Offline sweep preview; the planner is run once per P(reuse) source."""
    from kvevac.planner_trials import (
        KV_BYTES_PER_TOKEN,
        L40S_MEASURED,
        LINKS_MBPS,
        NOTICES_S,
        RESTORE_BPS,
        baseline_order,
        score,
    )
    from kvevac.vllm_plugin.core import FlushParams, FlushRequest, SessionIndex, plan_flush

    block = 256
    params = FlushParams(block_bytes=block * KV_BYTES_PER_TOKEN, block_tokens=block,
                         tier_bytes_per_s=1e9, tier_setup_s=0.3, gpu=L40S_MEASURED,
                         restore_bytes_per_s=RESTORE_BPS)
    policies = ["planner", *[f"planner_{name}" for name in probs], "recent", "largest",
                "random", "oracle"]
    result = {"snapshots": {}, "trials": []}
    seq = 0
    for trial in trials:
        prefix = f"s{trial['snapshot']}"
        sessions = {f"{prefix}-{i}": dict(s) for i, s in enumerate(trial["sessions"])}
        result["snapshots"][str(trial["snapshot"])] = sessions
        index = SessionIndex()
        for sid, s in sessions.items():
            for i in range(0, s["tokens"], block):
                index.record(sid, f"{sid}-{i}", i, 0.0)
        for link in LINKS_MBPS:
            for notice in NOTICES_S:
                for policy in policies:
                    seq += 1
                    reuse_p = None
                    if policy.startswith("planner_"):
                        source = probs[policy.removeprefix("planner_")]
                        reuse_p = {sid: source[s["key"]] for sid, s in sessions.items()}
                        order = None
                    else:
                        order = baseline_order(policy, sessions,
                                               f"{prefix}-{link}-{notice}")
                    req = FlushRequest(seq, 1000.0 + notice, order, only=list(sessions),
                                       idle_s={k: s["idle_s"] for k, s in sessions.items()},
                                       tier_bytes_per_s=link * 1e6, reuse_p=reuse_p)
                    flush, _ = plan_flush(index, req, params, now_unix=1000.0)
                    saved: dict[str, int] = defaultdict(int)
                    for sid in flush.key_sessions:
                        saved[sid] += block
                    result["trials"].append({
                        "snapshot": trial["snapshot"], "link_MBps": link,
                        "notice_s": notice, "policy": policy, "deadline_unix": 0,
                        "saved_tokens": dict(saved),
                        "report": {"keys_submitted": len(flush.keys),
                                   "keys_on_time": len(flush.keys)}})
    return value_table(score(result)["rows"], policies)


def value_table(rows: list[dict], policies: list[str]) -> dict:
    """Mean value per cell and policy, and each learned planner paired against the
    recency planner on the same snapshots (mean difference, 95% t half-width)."""
    out: dict[str, dict] = {}
    for link, notice in sorted({(r["link_MBps"], r["notice_s"]) for r in rows}):
        cell = [r for r in rows if r["link_MBps"] == link and r["notice_s"] == notice]
        name = f"{link:.0f}MB/s W={notice:.0f}s"
        by = defaultdict(dict)
        for r in cell:
            by[r["policy"]][r["snapshot"]] = r["value_s"]
        out[name] = {"means": {p: round(statistics.mean(by[p].values()), 3)
                               for p in policies if by[p]}, "vs_recency_planner": {}}
        out[name]["planner_vs_simple"] = {}
        for other in ("recent", "largest", "random"):
            diffs = [by["planner"][k] - by[other][k] for k in by["planner"] if k in by[other]]
            if len(diffs) > 1:
                half = 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs))
                out[name]["planner_vs_simple"][other] = {
                    "mean": round(statistics.mean(diffs), 3), "ci95": round(half, 3),
                    "ahead": sum(d > 0.005 for d in diffs),
                    "behind": sum(d < -0.005 for d in diffs), "n": len(diffs)}
        for p in policies:
            if not p.startswith("planner_"):
                continue
            diffs = [by[p][k] - by["planner"][k] for k in by["planner"] if k in by[p]]
            if len(diffs) > 1:
                half = 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs))
                out[name]["vs_recency_planner"][p] = {
                    "mean": round(statistics.mean(diffs), 3), "ci95": round(half, 3),
                    "ahead": sum(d > 0.005 for d in diffs),
                    "behind": sum(d < -0.005 for d in diffs), "n": len(diffs)}
    return out


def hardware_trials(rows: list[dict], key_of: dict[tuple, int], *, count: int,
                    seed: int) -> list[dict]:
    """The hardware sweep's exact snapshots: kvevac.planner_trials.export's selection,
    replayed on the same simulation, with each session tagged by its dataset row."""
    from kvevac.characterize import WARMUP_S
    from kvevac.planner_trials import CAPACITY_TOKENS, MAX_CONTEXT

    rows = [r for r in rows
            if r["t_s"] >= WARMUP_S and sum(1 for s in r["detail"] if not s["in_flight"]) >= 4]
    rng = random.Random(seed)
    trials = []
    for index, row in enumerate(rng.sample(rows, min(count, len(rows)))):
        idle = [s for s in row["detail"] if not s["in_flight"]]
        rng.shuffle(idle)
        chosen, used = [], 0
        for s in idle:
            tokens = min(int(s["tokens"]), MAX_CONTEXT)
            if tokens < 1_000 or used + tokens > CAPACITY_TOKENS:
                continue
            chosen.append({"tokens": tokens, "idle_s": s["idle_s"],
                           "returns": bool(s["returns"]),
                           "key": key_of[(row["t_s"], row["node"], s["id"])]})
            used += tokens
        trials.append({"snapshot": index, "sessions": chosen})
    return trials


def snapshot_trials(data: list[dict], *, count: int, seed: int,
                    min_sessions: int = 2) -> list[dict]:
    """Sweep-style snapshots (kvevac.planner_trials.export's packing): idle sessions of
    one node at one time, drawn at random until they fill a g6e.2xlarge CPU tier."""
    from kvevac.planner_trials import CAPACITY_TOKENS, MAX_CONTEXT

    by_snapshot: dict[tuple, list[dict]] = defaultdict(list)
    for r in data:
        by_snapshot[(r["t_s"], r["node"])].append(r)
    keys = [k for k, v in by_snapshot.items() if len(v) >= 4]
    rng = random.Random(seed)
    trials = []
    for index, key in enumerate(rng.sample(keys, min(count, len(keys)))):
        rows = list(by_snapshot[key])
        rng.shuffle(rows)
        chosen, used = [], 0
        for r in rows:
            tokens = min(r["tokens"], MAX_CONTEXT)
            if tokens < 1_000 or used + tokens > CAPACITY_TOKENS:
                continue
            chosen.append({"tokens": tokens, "idle_s": r["idle_s"],
                           "returns": r["returns"], "key": r["row"]})
            used += tokens
        if len(chosen) >= min_sessions:
            trials.append({"snapshot": index, "sessions": chosen})
    return trials


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--sessions", type=int, default=1600)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--snapshots", type=int, default=300,
                        help="offline sweep snapshots for the planner-value estimate")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    by_id, rows = simulate(args.trace, sessions=args.sessions, seed=args.seed)
    data = dataset(by_id, rows)
    for i, r in enumerate(data):
        r["row"] = i
    preds = cross_fit(data, folds=args.folds, seed=args.seed)
    metrics = classifier_metrics(data, preds)
    print(json.dumps(metrics, indent=1))

    probs = {name: dict(enumerate(p)) for name, p in preds.items() if name != "recency"}
    probs["oracle_p"] = {i: float(r["returns"]) for i, r in enumerate(data)}
    key_of = {(r["t_s"], r["node"], r["id"]): r["row"] for r in data}
    hardware = hardware_trials(rows, key_of, count=14, seed=args.seed)
    many = snapshot_trials(data, count=args.snapshots, seed=args.seed + 1)
    value = {"hardware_snapshots": {"n": len(hardware),
                                    "cells": planner_value(hardware, probs)},
             "offline_snapshots": {"n": len(many), "cells": planner_value(many, probs)}}
    print(json.dumps(value, indent=1))
    (args.out / "classifier.json").write_text(json.dumps(metrics, indent=1))
    (args.out / "planner_value.json").write_text(json.dumps(value, indent=1))


if __name__ == "__main__":
    main()
