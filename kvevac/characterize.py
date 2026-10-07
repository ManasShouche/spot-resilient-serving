"""Characterization: how much KV value sits on a spot node, and how much of it is idle.

This is contribution 1 in docs/positioning.md and it does not depend on any policy
winning. The fleet serves the workload with no reclaims; every `--every` seconds we
snapshot each node and record what a reclaim at that instant would put at risk:

- resident KV in GB, split into hot (running, or active within `hot_window_s`) and idle;
- prefill GPU-seconds needed to rebuild it, and the part belonging to sessions that
  really do return (the value an oracle would protect);
- the budget ratio rho = W x B / resident KV for each notice W and link B. rho < 1 is
  the regime where an evacuation planner has decisions to make (positioning 4.1).

Usage:
    python -m kvevac.characterize --seeds 3 --out results/characterize
    python -m kvevac.characterize --trace data/raw/agentx.jsonl --out results/characterize
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from kvevac.profiles import GPUS, LINKS, MODELS
from kvevac.sim import FleetConfig, Policy, Simulation
from kvevac.workload import load_agentx_jsonl, quantile, synthetic_sessions

WARMUP_S = 3600.0
"""Skip snapshots taken while the fleet is still filling up."""
ARRIVAL_WINDOW_S = 4 * 3600.0
"""Sessions start uniformly over this window; snapshots stop at its end, so they only
see the steady state (arrivals still coming), not the drain-down tail."""
NOTICES_S = (30.0, 120.0)
LINK_NAMES = ("10gbe", "25gbe", "object-store")


@dataclass(frozen=True)
class Scenario:
    label: str
    model: str
    gpu: str
    fleet: FleetConfig
    load_scale: float = 1.0
    """Fraction of --sessions to use. The simulator has no memory-based admission
    control, so a small node must get proportionally less load or its in-flight
    contexts overflow the cache."""


SCENARIOS = (
    # Default simulator node: GPU KV plus a large host tier.
    Scenario("8B on L40S, 4M-token cache", "llama-3.1-8b", "l40s", FleetConfig()),
    # What a g6e.xlarge can actually hold: ~30 GB GPU KV + ~20 GB host DRAM, about
    # 400k tokens of 8B KV (positioning 4.1).
    Scenario("8B on g6e.xlarge, 400k-token cache", "llama-3.1-8b", "l40s",
             FleetConfig(cache_tokens=400_000), load_scale=0.1),
    Scenario("70B on 4xH100, 4M-token cache", "llama-3.1-70b", "h100x4-70b",
             FleetConfig()),
)


def snapshots(scenario: Scenario, sessions, every_s: float) -> list[dict]:
    sim = Simulation(sessions, [], policy=Policy.RECOMPUTE, fleet=scenario.fleet,
                     model=MODELS[scenario.model], gpu=GPUS[scenario.gpu],
                     link=LINKS["25gbe"], snapshot_every_s=every_s,
                     snapshot_until_s=ARRIVAL_WINDOW_S)
    rows = [r for r in sim.run().at_risk if r["t_s"] >= WARMUP_S]
    # Ignore nodes with nothing on them: they say nothing about value at risk.
    return [r for r in rows if r["hot_GB"] + r["idle_GB"] > 0]


def summarize(rows: list[dict]) -> dict:
    def dist(values: list[float]) -> dict:
        return {"mean": round(statistics.mean(values), 2),
                "p50": round(quantile(values, 0.5), 2),
                "p90": round(quantile(values, 0.9), 2),
                "max": round(max(values), 2)}

    total_gb = [r["hot_GB"] + r["idle_GB"] for r in rows]
    total_s = [r["hot_recompute_s"] + r["idle_recompute_s"] for r in rows]
    idle_share = [r["idle_GB"] / t for r, t in zip(rows, total_gb, strict=True)]
    out = {
        "snapshots": len(rows),
        "resident_GB": dist(total_gb),
        "idle_share_of_GB": dist(idle_share),
        "recompute_gpu_s_at_risk": dist(total_s),
        "returning_recompute_gpu_s": dist([r["returning_recompute_s"] for r in rows]),
        "returning_share_of_gpu_s": dist([r["returning_recompute_s"] / t if t else 0.0
                                          for r, t in zip(rows, total_s, strict=True)]),
        "sessions_per_node": dist([float(r["sessions"]) for r in rows]),
        "in_flight_per_node": dist([float(r["in_flight"]) for r in rows]),
        "rho": {},
    }
    for link in LINK_NAMES:
        for notice in NOTICES_S:
            budget = notice * LINKS[link].bytes_per_s / 1e9
            rho = [budget / gb for gb in total_gb]
            out["rho"][f"{link}, W={notice:g}s"] = {
                "p50": round(quantile(rho, 0.5), 2),
                "share_below_1": round(sum(r < 1 for r in rho) / len(rho), 3),
            }
    return out


def render(results: dict[str, dict], workload: str) -> str:
    lines = [f"## Value at risk per spot node ({workload}; simulated, assumed constants)", "",
             "| scenario | resident GB p50 / p90 | idle share p50 | rebuild GPU-s p50 / p90 | "
             "returning share p50 | sessions p50 | ρ<1 share, 25GbE W=30s / 120s |",
             "|---|---|---|---|---|---|---|"]
    for label, s in results.items():
        rho = s["rho"]
        lines.append(
            f"| {label} | {s['resident_GB']['p50']} / {s['resident_GB']['p90']} | "
            f"{s['idle_share_of_GB']['p50']:.0%} | "
            f"{s['recompute_gpu_s_at_risk']['p50']} / {s['recompute_gpu_s_at_risk']['p90']} | "
            f"{s['returning_share_of_gpu_s']['p50']:.0%} | "
            f"{s['sessions_per_node']['p50']:.0f} | "
            f"{rho['25gbe, W=30s']['share_below_1']:.0%} / "
            f"{rho['25gbe, W=120s']['share_below_1']:.0%} |")
    lines += ["", "Hot: running, or active in the last 60 s. Returning share: the part of the "
              "rebuild cost that belongs to sessions with another turn (what an oracle would "
              "protect). ρ = W × B / resident KV; below 1, not everything fits in the notice "
              "and the planner's choices matter."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--sessions", type=int, default=1600,
                        help="sessions over the 4 h arrival window (1600: 400/h)")
    parser.add_argument("--every", type=float, default=300.0, help="snapshot period (s)")
    parser.add_argument("--trace", type=Path, help="AgentX JSONL instead of synthetic")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    workload = (f"real sessions from {args.trace.name}" if args.trace
                else "synthetic AgentX-calibrated workload")
    results = {}
    for scenario in SCENARIOS:
        rows = []
        count = max(1, round(args.sessions * scenario.load_scale))
        for seed in range(args.seeds):
            if args.trace:
                sessions = load_agentx_jsonl(args.trace, arrival_window_s=ARRIVAL_WINDOW_S,
                                             seed=seed, max_sessions=count)
            else:
                sessions = synthetic_sessions(count,
                                              arrival_window_s=ARRIVAL_WINDOW_S, seed=seed)
            rows += snapshots(scenario, sessions, args.every)
        results[scenario.label] = summarize(rows)
    table = render(results, workload)
    print(table)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "value_at_risk.md").write_text(table + "\n")
        (args.out / "value_at_risk.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
