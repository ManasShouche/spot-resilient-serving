import json

import pytest

from kvevac.calibration import fit_link, fit_prefill, load_calibration


def synthetic_prefill(p: float, knee: float, setup: float) -> list[tuple[float, float]]:
    return [(c, setup + c / p + c * c / (2 * p * knee))
            for c in (1_000, 4_000, 16_000, 32_000, 64_000, 128_000)]


def test_prefill_fit_recovers_throughput_and_knee() -> None:
    fit = fit_prefill(synthetic_prefill(9_000, 40_000, 0.15))
    assert fit.tokens_per_s == pytest.approx(9_000, rel=1e-6)
    assert fit.attention_knee_tokens == pytest.approx(40_000, rel=1e-6)
    assert fit.setup_s == pytest.approx(0.15, abs=1e-6)
    assert fit.max_rel_error < 1e-6


def test_link_fit_recovers_bandwidth_and_setup() -> None:
    link = fit_link("x", [(b, 0.3 + b / 2.4e9) for b in (1e8, 1e9, 5e9, 2e10)])
    assert link.bytes_per_s == pytest.approx(2.4e9, rel=1e-6)
    assert link.setup_s == pytest.approx(0.3, abs=1e-6)


def test_fits_reject_too_few_points() -> None:
    with pytest.raises(ValueError):
        fit_prefill([(1, 1), (2, 2)])
    with pytest.raises(ValueError):
        fit_link("x", [(1, 1)])


def test_load_calibration_builds_profiles(tmp_path) -> None:
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({
        "gpu": "l40s-measured",
        "prefill": synthetic_prefill(10_000, 32_000, 0.2),
        "decode_tokens_per_s": 55,
        "links": {"25gbe-measured": [[b, 0.25 + b / 2.2e9] for b in (1e8, 1e9, 1e10)]},
    }))
    cal = load_calibration(path)
    assert cal.gpu.prefill_tokens_per_s == pytest.approx(10_000, rel=1e-6)
    assert cal.gpu.decode_tokens_per_s == 55
    assert cal.links["25gbe-measured"].bytes_per_s == pytest.approx(2.2e9, rel=1e-6)
