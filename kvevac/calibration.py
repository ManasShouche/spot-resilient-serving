"""Fit simulator constants from measurements (Phase 2) and load them as profiles.

Measurement file (JSON), produced by scripts/measure_prefill.py and the transfer
benchmarks in docs/calibration.md:

    {
      "gpu": "l40s-measured",
      "prefill": [[context_tokens, seconds], ...],     # cold prefill, prefix cache off
      "decode_tokens_per_s": 58.0,
      "links": {"25gbe-measured": [[bytes, seconds], ...]}
    }

Prefill is fitted to t = a + c/p + c^2 / (2 p K), the cost model in
kvevac.costmodel (throughput p, attention knee K, setup a). Links are fitted to
t = s + bytes / B. Both are ordinary least squares, in the standard library only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kvevac.profiles import GpuProfile, LinkProfile


@dataclass(frozen=True)
class PrefillFit:
    setup_s: float
    tokens_per_s: float
    attention_knee_tokens: float
    max_rel_error: float


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (small dense systems)."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-300:
            raise ValueError("singular system: need more distinct measurement points")
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(col + 1, n):
            factor = a[row][col] / a[col][col]
            for k in range(col, n + 1):
                a[row][k] -= factor * a[col][k]
    out = [0.0] * n
    for row in range(n - 1, -1, -1):
        out[row] = (a[row][n] - sum(a[row][k] * out[k] for k in range(row + 1, n))) / a[row][row]
    return out


def _least_squares(features: list[list[float]], targets: list[float]) -> list[float]:
    # Scale columns so the normal equations stay well conditioned.
    scales = [max(abs(row[j]) for row in features) or 1.0 for j in range(len(features[0]))]
    scaled = [[row[j] / scales[j] for j in range(len(row))] for row in features]
    k = len(scales)
    normal = [[sum(r[i] * r[j] for r in scaled) for j in range(k)] for i in range(k)]
    rhs = [sum(r[i] * t for r, t in zip(scaled, targets, strict=True)) for i in range(k)]
    return [c / s for c, s in zip(_solve(normal, rhs), scales, strict=True)]


def fit_prefill(points: list[tuple[float, float]]) -> PrefillFit:
    if len(points) < 3:
        raise ValueError("need at least 3 (context, seconds) points")
    features = [[1.0, c, c * c] for c, _ in points]
    a, b, d = _least_squares(features, [t for _, t in points])
    if b <= 0:
        raise ValueError("fitted per-token cost is not positive; check the measurements")
    knee = b / (2 * d) if d > 0 else float("inf")
    worst = max(abs((a + b * c + d * c * c) - t) / t for c, t in points)
    return PrefillFit(a, 1 / b, knee, worst)


def fit_link(name: str, points: list[tuple[float, float]]) -> LinkProfile:
    if len(points) < 2:
        raise ValueError("need at least 2 (bytes, seconds) points")
    setup, per_byte = _least_squares([[1.0, x] for x, _ in points], [t for _, t in points])
    if per_byte <= 0:
        raise ValueError("fitted per-byte cost is not positive")
    return LinkProfile(name, bytes_per_s=1 / per_byte, setup_s=max(0.0, setup))


@dataclass(frozen=True)
class Calibration:
    gpu: GpuProfile
    prefill_fit: PrefillFit
    links: dict[str, LinkProfile]


def load_calibration(path: str | Path) -> Calibration:
    raw = json.loads(Path(path).read_text())
    fit = fit_prefill([tuple(p) for p in raw["prefill"]])
    knee = fit.attention_knee_tokens if fit.attention_knee_tokens != float("inf") else 1e12
    gpu = GpuProfile(raw["gpu"], prefill_tokens_per_s=fit.tokens_per_s,
                     attention_knee_tokens=knee,
                     decode_tokens_per_s=float(raw["decode_tokens_per_s"]))
    links = {name: fit_link(name, [tuple(p) for p in pts])
             for name, pts in raw.get("links", {}).items()}
    return Calibration(gpu, fit, links)
