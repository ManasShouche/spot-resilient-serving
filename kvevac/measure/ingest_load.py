"""Synthetic KV-ingest load: copy KV-sized chunks at a target rate until stopped.

Emulates the receiving side of an evacuation on a single host:
- mode "host": host-to-host copies into pinned memory, which is where vLLM's CPU tier
  lands evacuated KV (NIC -> host DRAM). Contends on host memory bandwidth.
- mode "h2d": pinned host -> GPU copies, which is what promoting that KV to the GPU
  costs. Contends on PCIe with the serving engine.

Run as a subprocess (requires torch + CUDA for "h2d"); it prints one JSON line with
the achieved rate when it receives SIGTERM.

    python -m kvevac.measure.ingest_load --mode h2d --rate-gbps 2.5
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["host", "h2d"], required=True)
    parser.add_argument("--rate-gbps", type=float, required=True,
                        help="target gigabytes per second (0 = as fast as possible)")
    parser.add_argument("--chunk-mb", type=int, default=256)
    args = parser.parse_args()

    import torch  # deferred: only needed on the GPU host

    numel = args.chunk_mb * 1024 * 1024 // 2
    src = torch.empty(numel, dtype=torch.bfloat16).pin_memory()
    if args.mode == "h2d":
        dst = torch.empty(numel, dtype=torch.bfloat16, device="cuda")
    else:
        dst = torch.empty(numel, dtype=torch.bfloat16).pin_memory()
    chunk_bytes = numel * 2
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    copied = 0
    started = time.perf_counter()
    while not stop:
        dst.copy_(src, non_blocking=False)
        if args.mode == "h2d":
            torch.cuda.synchronize()
        copied += chunk_bytes
        if args.rate_gbps > 0:
            ahead = copied / (args.rate_gbps * 1e9) - (time.perf_counter() - started)
            if ahead > 0:
                time.sleep(ahead)
    elapsed = time.perf_counter() - started
    print(json.dumps({"mode": args.mode, "target_gbps": args.rate_gbps,
                      "achieved_gbps": round(copied / elapsed / 1e9, 3),
                      "seconds": round(elapsed, 2)}), flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
