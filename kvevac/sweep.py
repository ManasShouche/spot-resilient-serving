"""Regime sweep: policies x notice x link x reclaim pattern, against a no-reclaim run.

The headline metric is *excess prefill GPU-seconds*: total prefill minus the same
workload's total with no reclaims. It counts every second of rebuilding a reclaim
caused, including displacement (evacuated or replicated KV pushing other sessions out
of a cache), which the per-session "lost" counters alone would miss.

Usage: python -m kvevac.sweep [--sessions 150] [--seeds 3] [--gpu l40s] [--model llama-3.1-8b]
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from kvevac.profiles import GPUS, LINKS, MODELS
from kvevac.sim import FleetConfig, Policy, correlated_reclaims, independent_reclaims, run
from kvevac.workload import synthetic_sessions

HORIZON_S = 6 * 3600.0


def fleet_groups(fleet: FleetConfig) -> dict[str, list[str]]:
    return {g: [f"{g}-n{i}" for i in range(fleet.nodes_per_group)] for g in fleet.groups}


def reclaims_for(pattern: str, fleet: FleetConfig, notice_s: float, seed: int):
    groups = fleet_groups(fleet)
    if pattern == "independent":
        nodes = [n for members in groups.values() for n in members]
        return independent_reclaims(nodes, rate_per_node_h=0.1, horizon_s=HORIZON_S,
                                    notice_s=notice_s, seed=seed)
    return correlated_reclaims(groups, bursts=3, horizon_s=HORIZON_S, notice_s=notice_s,
                               fraction=0.5, seed=seed)


def sweep(*, sessions: int, seeds: int, gpu: str, model: str, links: list[str],
          notices: list[float], patterns: list[str], replica_tokens: int = 0,
          cache_tokens: int = 2_000_000) -> list[dict]:
    fleet = FleetConfig(cache_tokens=cache_tokens, replica_tokens=replica_tokens)
    kwargs = dict(fleet=fleet, model=MODELS[model], gpu=GPUS[gpu])
    rows = []
    for seed in range(seeds):
        workload = synthetic_sessions(sessions, arrival_window_s=3600, seed=seed)
        base = run(workload, [], Policy.RECOMPUTE, link=LINKS[links[0]], **kwargs)
        for pattern in patterns:
            for notice in notices:
                reclaims = reclaims_for(pattern, fleet, notice, seed=1000 + seed)
                for link in links:
                    for policy in Policy:
                        m = run(workload, reclaims, policy, link=LINKS[link], **kwargs)
                        rows.append({
                            "seed": seed, "pattern": pattern, "notice_s": notice,
                            "link": link, "policy": policy.value,
                            "excess_prefill_gpu_s": m.prefill_gpu_s - base.prefill_gpu_s,
                            **m.summary(),
                        })
    return rows


def table(rows: list[dict]) -> str:
    keys = sorted({(r["pattern"], r["link"], r["notice_s"], r["policy"]) for r in rows})
    lines = ["| pattern | link | notice | policy | excess prefill GPU-s (mean ± sd) | "
             "killed turns | notice egress GB | replication egress GB |",
             "|---|---|---|---|---|---|---|---|"]
    for pattern, link, notice, policy in keys:
        sel = [r for r in rows if (r["pattern"], r["link"], r["notice_s"], r["policy"]) ==
               (pattern, link, notice, policy)]
        excess = [r["excess_prefill_gpu_s"] for r in sel]
        sd = statistics.stdev(excess) if len(excess) > 1 else 0.0
        lines.append(
            f"| {pattern} | {link} | {notice:g}s | {policy} | "
            f"{statistics.mean(excess):.0f} ± {sd:.0f} | "
            f"{statistics.mean(r['killed_turns'] for r in sel):.1f} | "
            f"{statistics.mean(r['notice_egress_GB'] for r in sel):.0f} | "
            f"{statistics.mean(r['replication_egress_GB'] for r in sel):.0f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=150)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--gpu", default="l40s", choices=sorted(GPUS))
    parser.add_argument("--model", default="llama-3.1-8b", choices=sorted(MODELS))
    parser.add_argument("--links", nargs="+", default=["10gbe", "25gbe"])
    parser.add_argument("--notices", nargs="+", type=float, default=[0, 30, 120])
    parser.add_argument("--patterns", nargs="+", default=["correlated", "independent"])
    parser.add_argument("--cache-tokens", type=int, default=2_000_000)
    parser.add_argument("--replica-tokens", type=int, default=0,
                        help="separate replica tier per node (0 = share primary cache)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rows = sweep(sessions=args.sessions, seeds=args.seeds, gpu=args.gpu, model=args.model,
                 links=args.links, notices=args.notices, patterns=args.patterns,
                 cache_tokens=args.cache_tokens, replica_tokens=args.replica_tokens)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=1))
    print(table(rows))


if __name__ == "__main__":
    main()
