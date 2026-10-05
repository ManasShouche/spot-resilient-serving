"""Render paper figures from results/phase1b/*.json as static SVG (stdlib only).

Colors: the first three slots of the validated reference categorical palette
(blue, orange, aqua), which pass the all-pairs CVD checks. Each series is also
direct-labelled, so identity never rests on color alone. Light surface only, with an
explicit background, so the figures read the same in GitHub's light and dark themes.

Usage: python scripts/figures.py
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from kvevac.experiments import paired

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "phase1b"
OUT = ROOT / "docs" / "figures"

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
W, H = 720, 420
LEFT, RIGHT, TOP, BOTTOM = 72, 150, 76, 64


def reduction(per_seed: list[dict], policy: str) -> tuple[float, float]:
    """Percent reduction of excess prefill vs recompute, and its 95% CI half-width."""
    ref = [seed["recompute"]["excess"] for seed in per_seed]
    vals = [seed[policy]["excess"] for seed in per_seed]
    delta, half = paired(vals, ref)
    base = statistics.mean(ref)
    return -100 * delta / base, 100 * half / base


def svg(body: list[str], title: str, subtitle: str) -> str:
    """`subtitle` may contain one newline; each line renders on its own row."""
    lines = subtitle.split("\n")
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'height="{H}" font-family="Inter, system-ui, sans-serif" role="img" '
        f'aria-label="{title}">',
        f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>',
        f'<text x="{LEFT}" y="24" font-size="15" font-weight="600" fill="{INK}">{title}</text>',
        *[f'<text x="{LEFT}" y="{44 + 15 * i}" font-size="11.5" fill="{MUTED}">{line}</text>'
          for i, line in enumerate(lines)],
        *body,
        "</svg>",
    ])


def y_axis(lo: float, hi: float, step: float, label: str) -> tuple[list[str], callable]:
    plot_h = H - TOP - BOTTOM

    def y(value: float) -> float:
        return TOP + plot_h * (1 - (value - lo) / (hi - lo))

    out = []
    tick = lo
    while tick <= hi + 1e-9:
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
                   f'stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{LEFT - 8}" y="{y(tick) + 4:.1f}" font-size="11" fill="{MUTED}" '
                   f'text-anchor="end">{tick:.0f}%</text>')
        tick += step
    out.append(f'<text transform="translate(18,{TOP + plot_h / 2}) rotate(-90)" font-size="11.5" '
               f'fill="{MUTED}" text-anchor="middle">{label}</text>')
    return out, y


def figure_budget() -> str:
    data = json.loads((RESULTS / "budget.json").read_text())
    links = ["10gbe", "25gbe", "100gbe"]
    names = {"10gbe": "10GbE", "25gbe": "25GbE", "100gbe": "100GbE"}
    lo_x, hi_x = math.log10(0.03), math.log10(6)
    plot_w = W - LEFT - RIGHT

    def x(rho: float) -> float:
        return LEFT + plot_w * (math.log10(rho) - lo_x) / (hi_x - lo_x)

    body, y = y_axis(-10, 80, 10, "Reduction in reclaim-induced recompute")
    for rho in (0.05, 0.1, 0.25, 0.5, 1, 2, 4):
        body.append(f'<text x="{x(rho):.1f}" y="{H - BOTTOM + 18}" font-size="11" '
                    f'fill="{MUTED}" text-anchor="middle">{rho:g}</text>')
    body.append(f'<line x1="{x(1):.1f}" x2="{x(1):.1f}" y1="{TOP}" y2="{H - BOTTOM}" '
                f'stroke="{MUTED}" stroke-dasharray="3 3" stroke-width="1"/>')
    body.append(f'<text x="{x(1) + 4:.1f}" y="{TOP + 12}" font-size="10.5" fill="{MUTED}">'
                f'ρ = 1: notice moves all resident KV</text>')
    body.append(f'<text x="{LEFT + plot_w / 2}" y="{H - 22}" font-size="11.5" fill="{MUTED}" '
                f'text-anchor="middle">ρ = notice × link bandwidth / KV resident on the node '
                f'(log scale)</text>')
    for color, link in zip(SERIES, links, strict=True):
        points = []
        for label, per_seed in data.items():
            if not label.startswith(link + ","):
                continue
            rho = statistics.mean(s["evacuate"]["budget_ratio_mean"] for s in per_seed)
            mean, half = reduction(per_seed, "evacuate")
            points.append((rho, mean, half))
        points.sort()
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(r):.1f},{y(m):.1f}"
                        for i, (r, m, _) in enumerate(points))
        body.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>')
        for rho, mean, half in points:
            body.append(f'<line x1="{x(rho):.1f}" x2="{x(rho):.1f}" y1="{y(mean - half):.1f}" '
                        f'y2="{y(mean + half):.1f}" stroke="{color}" stroke-width="1.5" '
                        f'opacity="0.55"/>')
            body.append(f'<circle cx="{x(rho):.1f}" cy="{y(mean):.1f}" r="4.5" fill="{color}" '
                        f'stroke="{SURFACE}" stroke-width="2"><title>{names[link]}, ρ={rho:.2f}: '
                        f'{mean:.0f}% ± {half:.0f}</title></circle>')
        last = points[-1]
        body.append(f'<text x="{x(last[0]) + 10:.1f}" y="{y(last[1]) + 4:.1f}" font-size="12" '
                    f'fill="{INK}">{names[link]}</text>')
    return svg(body, "Evacuation's benefit is governed by the notice budget ρ",
               "Evacuate vs recompute, 12 seeds, mean ± 95% CI (paired).\n"
               "Simulated: synthetic agent workload, assumed hardware constants.")


def figure_backpressure() -> str:
    data = json.loads((RESULTS / "backpressure.json").read_text())
    order = ["unlimited", "200 MB/s", "83 MB/s", "40 MB/s"]
    policies = [("replicate", "write-through"), ("hybrid", "hybrid"),
                ("evacuate", "evacuate only")]
    plot_w = W - LEFT - RIGHT

    def x(index: int) -> float:
        return LEFT + plot_w * (index + 0.5) / len(order)

    body, y = y_axis(0, 80, 10, "Reduction in reclaim-induced recompute")
    for index, name in enumerate(order):
        sub = " (shared store)" if name == "83 MB/s" else ""
        body.append(f'<text x="{x(index):.1f}" y="{H - BOTTOM + 18}" font-size="11" '
                    f'fill="{MUTED}" text-anchor="middle">{name}{sub}</text>')
    body.append(f'<text x="{LEFT + plot_w / 2}" y="{H - 22}" font-size="11.5" fill="{MUTED}" '
                f'text-anchor="middle">Per-node write-through bandwidth budget '
                f'(drop on backpressure); notice W = 120 s</text>')
    for series_index, (color, (policy, label)) in enumerate(
            zip(SERIES, policies, strict=True)):
        dodge = (series_index - 1) * 9  # keep each series' CI bars apart

        def xd(index: int, dodge: float = dodge) -> float:
            return x(index) + dodge

        points = []
        for index, name in enumerate(order):
            per_seed = data[f"replication {name}, W=120s"]
            mean, half = reduction(per_seed, policy)
            points.append((index, mean, half))
        path = " ".join(f"{'M' if i == 0 else 'L'}{xd(k):.1f},{y(m):.1f}"
                        for i, (k, m, _) in enumerate(points))
        body.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>')
        for index, mean, half in points:
            body.append(f'<line x1="{xd(index):.1f}" x2="{xd(index):.1f}" '
                        f'y1="{y(mean - half):.1f}" y2="{y(mean + half):.1f}" stroke="{color}" '
                        f'stroke-width="1.5" opacity="0.55"/>')
            body.append(f'<circle cx="{xd(index):.1f}" cy="{y(mean):.1f}" r="4.5" '
                        f'fill="{color}" stroke="{SURFACE}" stroke-width="2"><title>{label}, '
                        f'{order[index]}: {mean:.0f}% ± {half:.0f}</title></circle>')
        last = points[-1]
        body.append(f'<text x="{x(last[0]) + 22:.1f}" y="{y(last[1]) + 4:.1f}" font-size="12" '
                    f'fill="{INK}">{label}</text>')
    return svg(body, "Write-through degrades under a bandwidth budget; hybrid does not",
               "Policy vs recompute, 12 seeds, mean ± 95% CI (paired).\n"
               "Simulated: synthetic agent workload, assumed hardware constants.")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "budget_ratio.svg").write_text(figure_budget())
    (OUT / "backpressure.svg").write_text(figure_backpressure())
    print(f"wrote {OUT / 'budget_ratio.svg'} and {OUT / 'backpressure.svg'}")


if __name__ == "__main__":
    main()
