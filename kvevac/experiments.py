"""Named Phase 1b experiments with paired statistics.

Every policy in a seed sees the same workload and the same reclaim schedule, so
comparisons are *paired*: we report the per-seed difference in excess prefill
GPU-seconds between two policies, with a 95% t-interval over seeds. Paired intervals
are far tighter than comparing two unpaired means with large between-seed variance.

Usage:
    python -m kvevac.experiments main        --seeds 8
    python -m kvevac.experiments budget      --seeds 6
    python -m kvevac.experiments sensitivity --seeds 6
    python -m kvevac.experiments reuse       --seeds 6
    python -m kvevac.experiments all         --seeds 6 --out results/phase1b
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from kvevac.profiles import GPUS, LINKS, MODELS
from kvevac.reuse import ReuseModel
from kvevac.sim import FleetConfig, Policy, correlated_reclaims, run
from kvevac.sweep import fleet_groups, reclaims_for
from kvevac.workload import synthetic_sessions

# Two-sided 95% t critical values by degrees of freedom.
_T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26,
        10: 2.23, 12: 2.18, 15: 2.13, 20: 2.09, 30: 2.04}


def t95(df: int) -> float:
    if df in _T95:
        return _T95[df]
    return next((v for k, v in sorted(_T95.items()) if k >= df), 1.96)


@dataclass(frozen=True)
class Setting:
    label: str
    notice_s: float = 120.0
    pattern: str = "independent"
    link: str = "25gbe"
    model: str = "llama-3.1-8b"
    gpu: str = "l40s"
    sessions: int = 800
    fleet: FleetConfig = FleetConfig(replica_tokens=4_000_000)
    burst_fraction: float = 0.5


def excess_by_policy(setting: Setting, seed: int,
                     policies: Iterable[Policy] = tuple(Policy)) -> dict[str, dict]:
    workload = synthetic_sessions(setting.sessions, arrival_window_s=7200, seed=seed)
    kwargs = dict(fleet=setting.fleet, model=MODELS[setting.model], gpu=GPUS[setting.gpu],
                  link=LINKS[setting.link])
    base = run(workload, [], Policy.RECOMPUTE, **kwargs)
    if setting.pattern == "correlated":
        reclaims = correlated_reclaims(fleet_groups(setting.fleet), bursts=3,
                                       horizon_s=6 * 3600, notice_s=setting.notice_s,
                                       fraction=setting.burst_fraction, seed=1000 + seed)
    else:
        reclaims = reclaims_for("independent", setting.fleet, setting.notice_s, 1000 + seed)
    out = {}
    for policy in policies:
        metrics = run(workload, reclaims, policy, **kwargs)
        summary = metrics.summary()
        summary["excess"] = metrics.prefill_gpu_s - base.prefill_gpu_s
        summary["ttft_mean_excess"] = summary["ttft_mean_s"] - base.summary()["ttft_mean_s"]
        out[policy.value] = summary
    return out


def paired(values_a: list[float], values_b: list[float]) -> tuple[float, float]:
    """Mean of (a - b) and half-width of its 95% t-interval."""
    diffs = [a - b for a, b in zip(values_a, values_b, strict=True)]
    if len(diffs) < 2:
        return diffs[0] if diffs else 0.0, float("nan")
    half = t95(len(diffs) - 1) * statistics.stdev(diffs) / math.sqrt(len(diffs))
    return statistics.mean(diffs), half


def _job(args: tuple[Setting, int, tuple[Policy, ...]]) -> dict[str, dict]:
    setting, seed, policies = args
    return excess_by_policy(setting, seed, policies)


def run_settings(settings: list[Setting], seeds: int,
                 policies: Iterable[Policy] = tuple(Policy),
                 jobs: int = 1) -> dict[str, list[dict]]:
    """Run every (setting, seed) pair; `jobs > 1` fans out over processes."""
    tasks = [(setting, seed, tuple(policies)) for setting in settings
             for seed in range(seeds)]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            outputs = list(pool.map(_job, tasks))
    else:
        outputs = [_job(task) for task in tasks]
    results: dict[str, list[dict]] = {}
    for (setting, _, _), output in zip(tasks, outputs, strict=True):
        results.setdefault(setting.label, []).append(output)
    return results


def render(results: dict[str, list[dict]], *, reference: str = "recompute",
           policies: Iterable[str] | None = None) -> str:
    lines = [
        "| setting | policy | excess prefill GPU-s (mean) | vs recompute: Δ ± 95% CI | "
        "Δ% | ΔTTFT mean (s) | killed turns | notice GB | replication GB | budget ratio |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, per_seed in results.items():
        names = list(policies or per_seed[0].keys())
        ref = [seed[reference]["excess"] for seed in per_seed]
        ref_mean = statistics.mean(ref)
        for name in names:
            rows = [seed[name] for seed in per_seed]
            vals = [r["excess"] for r in rows]
            delta, half = paired(vals, ref)
            pct = 100 * delta / ref_mean if ref_mean else float("nan")
            ci = "—" if name == reference else f"{delta:+.0f} ± {half:.0f}"
            pct_text = "—" if name == reference else f"{pct:+.0f}%"
            lines.append(
                f"| {label} | {name} | {statistics.mean(vals):.0f} | {ci} | {pct_text} | "
                f"{statistics.mean(r['ttft_mean_excess'] for r in rows):+.2f} | "
                f"{statistics.mean(r['killed_turns'] for r in rows):.1f} | "
                f"{statistics.mean(r['notice_egress_GB'] for r in rows):.0f} | "
                f"{statistics.mean(r['replication_egress_GB'] for r in rows):.0f} | "
                f"{statistics.mean(r['budget_ratio_mean'] for r in rows):.2f} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------- experiments
def exp_main() -> list[Setting]:
    return [Setting(f"{pattern}, W={notice:g}s", notice_s=notice, pattern=pattern)
            for pattern in ("independent", "correlated") for notice in (0, 30, 120)]


def exp_budget() -> list[Setting]:
    """Vary notice and bandwidth to trace evacuation benefit against W*B/resident KV."""
    return [Setting(f"{link}, W={notice:g}s", notice_s=notice, link=link)
            for link in ("10gbe", "25gbe", "100gbe") for notice in (15, 30, 60, 120)]


def exp_sensitivity() -> list[Setting]:
    base = FleetConfig(replica_tokens=4_000_000)
    return [
        Setting("cache 2M", fleet=replace(base, cache_tokens=2_000_000,
                                          replica_tokens=2_000_000)),
        Setting("cache 8M", fleet=replace(base, cache_tokens=8_000_000,
                                          replica_tokens=8_000_000)),
        Setting("load 400 sessions", sessions=400),
        Setting("load 1200 sessions", sessions=1200),
        Setting("70B on 4xH100", model="llama-3.1-70b", gpu="h100x4-70b"),
        Setting("whole-group bursts", pattern="correlated", burst_fraction=1.0),
        Setting("quarter-group bursts", pattern="correlated", burst_fraction=0.25),
        Setting("replica tier 1M", fleet=replace(base, replica_tokens=1_000_000)),
    ]


def exp_reuse() -> list[Setting]:
    base = FleetConfig(replica_tokens=4_000_000)
    return [Setting(f"{model.value}, W={notice:g}s", notice_s=notice,
                    fleet=replace(base, reuse_model=model))
            for notice in (30, 120) for model in ReuseModel]


EXPERIMENTS = {
    "main": (exp_main, None),
    "budget": (exp_budget, (Policy.RECOMPUTE, Policy.EVACUATE)),
    "sensitivity": (exp_sensitivity, None),
    "reuse": (exp_reuse, (Policy.RECOMPUTE, Policy.EVACUATE)),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment", choices=[*EXPERIMENTS, "all"])
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    names = list(EXPERIMENTS) if args.experiment == "all" else [args.experiment]
    for name in names:
        build, policies = EXPERIMENTS[name]
        started = time.time()
        results = run_settings(build(), args.seeds, policies or tuple(Policy), args.jobs)
        table = render(results)
        header = (f"## {name} ({args.seeds} seeds, synthetic AgentX-calibrated workload, "
                  f"assumed hardware constants; {time.time() - started:.0f}s)\n\n")
        print(header + table + "\n", flush=True)
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{name}.md").write_text(header + table + "\n")
            (args.out / f"{name}.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
