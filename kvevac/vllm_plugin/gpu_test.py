"""First GPU test of the deadline write-back plugin, on one node.

Three vLLM processes share one filesystem tier (`--tier`, ideally local NVMe):

A  deferred mode. Serves turn 1 of two agent sessions. Checks that nothing reached the
   tier before the notice, then writes a flush request with a deadline and waits for
   the plugin's status report. Killed with SIGKILL, standing in for the spot reclaim.
B  fresh process, same tier: serves turn 2 of each session, restoring the evacuated
   prefix from the tier instead of recomputing it.
C  fresh process, empty tier: serves the same turn 2 cold (the recompute baseline).

Reported (results/phase3.json): tier write bandwidth, tier files before and after the
flush, the flush report, TTFT of turn 2 restored (B) vs cold (C), and whether the
greedy outputs of B and C match (output parity).

    python -m kvevac.vllm_plugin.gpu_test --model <name> --tier /mnt/nvme/tier --out <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from kvevac.vllm_plugin.core import FlushRequest, write_flush_request

WORDS = ("agent tool call result file patch test build error fix commit review diff plan "
         "search read write query table index cache token model layer server client "
         "request response retry timeout queue worker thread lock memory disk network "
         "spot node notice deadline session prefix block hash store load evict").split()
SESSIONS = {"s-long": 56_000, "s-short": 20_000}
"""Turn-1 prompt words per session (about 1-1.2 tokens per word with Llama-3)."""
MAX_MODEL_LEN = 98_304
SHM = "/dev/shm"
TURN2_SUFFIX_WORDS = 1_500
OUTPUT_TOKENS = 48


def log(msg: str) -> None:
    print(f"[gpu_test {time.strftime('%H:%M:%S')}] {msg}", flush=True)
    console = os.environ.get("KVEVAC_CONSOLE")
    if console:  # progress line for the runner, same shape as instance_job.sh's events
        line = json.dumps({"event": "job", "at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                                                time.gmtime()),
                           "stage": "phase3", "msg": msg.replace('"', "'")[:200]})
        try:
            with open(console, "a") as handle:
                handle.write(f"KVEVAC {line}\n")
        except OSError:
            pass


def text(seed: str, words: int) -> str:
    rng = random.Random(seed)
    return " ".join(rng.choice(WORDS) for _ in range(words))


def complete(port: int, model: str, prompt: str, session: str, max_tokens: int,
             timeout_s: float = 900.0) -> dict:
    body = json.dumps({
        "model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0,
        "stream": True, "stream_options": {"include_usage": True}, "logprobs": 2,
        "kv_transfer_params": {"kvevac_session_id": session},
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    sent = time.perf_counter()
    ttft, out, usage, top = None, [], {}, []
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            chunk = json.loads(line[5:])
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices", []):
                if choice.get("text"):
                    ttft = ttft or time.perf_counter() - sent
                    out.append(choice["text"])
                    # Top-2 logprobs per token: tells a near-tie flip from a real error
                    # when restored and cold outputs diverge.
                    for alts in (choice.get("logprobs") or {}).get("top_logprobs") or []:
                        top.append({k: round(v, 4) for k, v in (alts or {}).items()})
    return {"ttft_s": round(ttft or -1, 4), "text": "".join(out), "top_logprobs": top[:16],
            "prompt_tokens": usage.get("prompt_tokens"),
            "total_s": round(time.perf_counter() - sent, 4)}


def throttle(dev: str | None, mbit: int | None) -> None:
    """Cap this node's egress on `dev` (tc tbf), or remove the cap when mbit is None.
    Used to force a tight budget (rho < 1) while process A evacuates."""
    if not dev:
        return
    subprocess.run(["tc", "qdisc", "del", "dev", dev, "root"], capture_output=True)
    if mbit:
        subprocess.run(["tc", "qdisc", "add", "dev", dev, "root", "tbf", "rate", f"{mbit}mbit",
                        "burst", "1mb", "latency", "500ms"], check=True, capture_output=True)
        log(f"egress on {dev} capped at {mbit} Mbit/s")
    else:
        log(f"egress cap on {dev} removed")


def tier_stats(tier: Path) -> dict:
    files = size = 0
    for path in tier.rglob("*.bin"):
        files += 1
        size += path.stat().st_size
    return {"files": files, "GB": round(size / 1e9, 3)}


def write_bandwidth(tier: Path, gb: int = 4) -> float:
    """Sustained O_DIRECT write bandwidth of the tier's device, bytes/s."""
    target = tier.parent / "bw.test"
    started = time.perf_counter()
    try:
        subprocess.run(["dd", "if=/dev/zero", f"of={target}", "bs=64M",
                        f"count={gb * 16}", "oflag=direct"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):  # no O_DIRECT: buffered + fsync
        block = b"\0" * 64 * 2**20
        with target.open("wb") as handle:
            for _ in range(gb * 16):
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
    elapsed = time.perf_counter() - started
    target.unlink(missing_ok=True)
    return gb * 16 * 64 * 2**20 / elapsed


class Server:
    def __init__(self, name: str, port: int, args: argparse.Namespace, tier: Path,
                 mode: str, control: Path | None, tier_bps: float, *,
                 extra: dict | None = None, max_model_len: int | None = None) -> None:
        cfg = {
            "kv_connector": "OffloadingConnector", "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "spec_name": "DeadlineTieringOffloadingSpec",
                "spec_module_path": "kvevac.vllm_plugin.manager",
                "cpu_bytes_to_use": int(args.cpu_gb * 2**30),
                "secondary_tiers": [{"type": "fs", "root_dir": str(tier)}],
                "kvevac": {"cascade_mode": mode, "tier_bytes_per_s": tier_bps,
                           **({"control_path": str(control)} if control else {}),
                           **(extra or {})},
            },
        }
        cmd = [args.python, "-m", "vllm.entrypoints.openai.api_server", "--model",
               args.model, "--port", str(port),
               "--max-model-len", str(max_model_len or args.max_model_len),
               "--gpu-memory-utilization", str(getattr(args, "gpu_util", 0.85)),
               "--kv-transfer-config", json.dumps(cfg)]
        env = {**os.environ, "PYTHONHASHSEED": "0", "VLLM_USE_FLASHINFER_SAMPLER": "0"}
        self.name, self.port = name, port
        self.log_path = Path(args.logs) / f"vllm-{name}.log"
        log(f"starting {name} ({mode}) on :{port}")
        self.shm_before = set(os.listdir(SHM)) if os.path.isdir(SHM) else set()
        self.proc = subprocess.Popen(cmd, env=env, stdout=self.log_path.open("w"),
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self.wait_healthy()

    def wait_healthy(self, timeout_s: float = 1200.0) -> None:
        end = time.time() + timeout_s
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.name} died during startup; see {self.log_path}")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2)
                log(f"{self.name} healthy")
                return
            except OSError:
                time.sleep(5)
        raise RuntimeError(f"{self.name} not healthy after {timeout_s:.0f} s")

    def kill(self) -> None:
        """SIGKILL the whole process group: no graceful shutdown, like a reclaim."""
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait()
        time.sleep(5)  # let the GPU memory be released
        # A SIGKILLed vLLM leaves its CPU-tier shared region in /dev/shm (14 GB here),
        # and the next process cannot allocate its own. On a real reclaim the machine
        # is gone; on this single-node stand-in, remove what the dead process left.
        if os.path.isdir(SHM):
            for name in set(os.listdir(SHM)) - self.shm_before:
                try:
                    os.unlink(os.path.join(SHM, name))
                except OSError:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tier", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cpu-gb", type=float, default=14.0)
    parser.add_argument("--scale", type=float, default=1.0,
                        help="multiply the sessions' prompt lengths (RAM-tier runs need <1)")
    parser.add_argument("--notice-s", type=float, default=120.0)
    parser.add_argument("--sessions", help="'id:words,...' in serving order (default: two "
                        "sessions, 56k and 20k words)")
    parser.add_argument("--max-model-len", type=int, default=MAX_MODEL_LEN)
    parser.add_argument("--gpu-util", type=float, default=0.85,
                        help="vLLM --gpu-memory-utilization (24 GB GPUs need ~0.92)")
    parser.add_argument("--throttle-dev", help="network device to cap while A evacuates")
    parser.add_argument("--rate-mbit", type=int, help="egress cap in Mbit/s (needs --throttle-dev)")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cold-tier", type=Path,
                        help="tier for the cold baseline (default: next to --tier)")
    parser.add_argument("--logs", type=Path, default=Path("."),
                        help="where the vLLM server logs go (keep them out of --out)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    global SESSIONS
    if args.sessions:
        SESSIONS = {sid: int(words) for sid, words in
                    (item.split(":") for item in args.sessions.split(","))}
    SESSIONS = {sid: int(words * args.scale) for sid, words in SESSIONS.items()}
    result: dict = {"model": args.model, "sessions": SESSIONS, "tier": str(args.tier),
                    "cpu_gb": args.cpu_gb, "notice_s": args.notice_s,
                    "egress_cap_mbit": args.rate_mbit}
    report_path = args.out / "phase3.json"

    def save() -> None:
        report_path.write_text(json.dumps(result, indent=1))

    tier, cold_tier = args.tier, args.cold_tier or args.tier.parent / "cold-tier"
    for path in (tier, cold_tier):
        path.mkdir(parents=True, exist_ok=True)
    control = args.out / "flush.json"
    throttle(args.throttle_dev, args.rate_mbit)  # the planner sees the capped bandwidth
    bps = write_bandwidth(tier)
    result["tier_write_GBps"] = round(bps / 1e9, 3)
    log(f"tier write bandwidth {bps / 1e9:.2f} GB/s")
    save()

    turn1 = {sid: text(sid, words) for sid, words in SESSIONS.items()}
    server = Server("A", 8001, args, tier, "deferred", control, bps)
    try:
        result["turn1"] = {}
        for sid, prompt in turn1.items():
            result["turn1"][sid] = complete(8001, args.model, prompt, sid, OUTPUT_TOKENS)
            log(f"turn 1 {sid}: {result['turn1'][sid]['prompt_tokens']} tokens, "
                f"TTFT {result['turn1'][sid]['ttft_s']} s")
        time.sleep(10)  # let GPU->CPU stores land
        result["tier_before_flush"] = tier_stats(tier)
        deadline = time.time() + args.notice_s
        result["deadline_unix"] = deadline
        write_flush_request(control, FlushRequest(seq=1, deadline_unix=deadline))
        noticed = time.time()
        # A one-token request makes the scheduler step, so it polls the control file.
        complete(8001, args.model, "wake", "wake", 1)
        status = control.with_suffix(control.suffix + ".status")
        report = None
        while time.time() < deadline:
            try:
                report = json.loads(status.read_text())
            except (OSError, ValueError):
                report = None
            if report and report.get("finished_unix"):
                break
            time.sleep(1)
            complete(8001, args.model, "wake", "wake", 1)  # keep the scheduler stepping
        result["flush"] = report
        result["flush_wall_s"] = round(time.time() - noticed, 2)
        if report and report.get("finished_unix"):
            result["finished_before_deadline_s"] = round(deadline - report["finished_unix"], 2)
        result["tier_after_flush"] = tier_stats(tier)
        log(f"flush report: {json.dumps(report)[:400]}")
    finally:
        server.kill()
        throttle(args.throttle_dev, None)  # restore and the cold baseline run uncapped
        save()

    turn2 = {sid: turn1[sid] + result["turn1"][sid]["text"] + " "
             + text(sid + "-turn2", TURN2_SUFFIX_WORDS) for sid in SESSIONS}
    for name, port, root, key in (("B", 8002, tier, "restored"),
                                  ("C", 8003, cold_tier, "cold")):
        server = Server(name, port, args, root, "write_through", None, bps)
        try:
            result[key] = {sid: complete(port, args.model, prompt, sid, OUTPUT_TOKENS)
                           for sid, prompt in turn2.items()}
            for sid, row in result[key].items():
                log(f"turn 2 {key} {sid}: {row['prompt_tokens']} tokens, TTFT {row['ttft_s']} s")
        finally:
            server.kill()
            save()
    result["output_parity"] = {sid: result["restored"][sid]["text"] == result["cold"][sid]["text"]
                               for sid in SESSIONS}
    result["ttft_speedup"] = {sid: round(result["cold"][sid]["ttft_s"]
                                         / max(1e-6, result["restored"][sid]["ttft_s"]), 2)
                              for sid in SESSIONS}
    save()
    log(f"parity {result['output_parity']}, TTFT speedup {result['ttft_speedup']}")


if __name__ == "__main__":
    main()
