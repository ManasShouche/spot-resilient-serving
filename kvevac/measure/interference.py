"""Measure receiver-side slowdown: cold-prefill TTFT with and without KV-ingest load.

For each ingest rate, a load generator (kvevac.measure.ingest_load) runs while we send
cold prompts of a fixed context length and record TTFT. The slowdown at rate r is
median TTFT(r) / median TTFT(idle) - 1, which is FleetConfig.ingress_slowdown.

    python -m kvevac.measure.interference --base-url http://localhost:8000 \\
        --model <name> --context 32000 --repeats 5 --rates 1 2.5 10 0 \\
        --mode host --out results/calibration/interference.json

A rate of 0 means "as fast as the copy loop can go" (an upper bound).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ContextManager

from kvevac.measure.prefill import _stream_completion, cold_prompt

LoadStarter = Callable[[float], ContextManager[dict]]


@contextlib.contextmanager
def subprocess_load(mode: str) -> Callable[[float], Iterator[dict]]:
    """Factory for a load starter that runs ingest_load in a child process."""

    @contextlib.contextmanager
    def start(rate_gbps: float) -> Iterator[dict]:
        proc = subprocess.Popen(
            [sys.executable, "-m", "kvevac.measure.ingest_load", "--mode", mode,
             "--rate-gbps", str(rate_gbps)],
            stdout=subprocess.PIPE, text=True)
        report: dict = {}
        try:
            time.sleep(3.0)  # let allocation and pinning finish before measuring
            yield report
        finally:
            proc.terminate()
            out, _ = proc.communicate(timeout=60)
            lines = [line for line in out.splitlines() if line.startswith("{")]
            if lines:
                report.update(json.loads(lines[-1]))

    yield start


def measure_interference(base_url: str, model: str, *, context: int, repeats: int,
                         rates: list[float], start_load: Callable[[float], ContextManager],
                         timeout_s: float = 600.0) -> dict:
    def ttfts() -> list[float]:
        return [_stream_completion(base_url, model, cold_prompt(context), 1, timeout_s)[0]
                for _ in range(repeats)]

    idle = ttfts()
    idle_median = statistics.median(idle)
    rows = [{"rate_gbps": None, "label": "idle", "ttft_s": idle,
             "ttft_median_s": idle_median, "slowdown": 0.0}]
    for rate in rates:
        with start_load(rate) as report:
            loaded = ttfts()
        median = statistics.median(loaded)
        rows.append({"rate_gbps": rate, "label": "max" if rate == 0 else f"{rate:g} GB/s",
                     "ttft_s": loaded, "ttft_median_s": median,
                     "slowdown": round(median / idle_median - 1, 4), "load": dict(report),
                     # No achieved rate means the load generator died: the "slowdown" is
                     # then meaningless and must not be used for calibration.
                     "load_failed": "achieved_gbps" not in report})
    return {"context_tokens": context, "repeats": repeats, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--context", type=int, default=32_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--rates", type=float, nargs="+", default=[1.0, 2.5, 10.0, 0.0])
    parser.add_argument("--mode", choices=["host", "h2d"], default="host")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with subprocess_load(args.mode) as start:
        result = measure_interference(args.base_url, args.model, context=args.context,
                                      repeats=args.repeats, rates=args.rates,
                                      start_load=start)
    result["mode"] = args.mode
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))
    for row in result["rows"]:
        flag = "  [LOAD FAILED: ignore this row]" if row.get("load_failed") else ""
        print(f"{row['label']:>10}: TTFT median {row['ttft_median_s']:.3f}s, "
              f"slowdown {row['slowdown']:+.1%}{flag}")


if __name__ == "__main__":
    main()
