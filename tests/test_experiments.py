import math

import pytest

from kvevac.experiments import Setting, paired, render, run_settings, t95
from kvevac.sim import Policy


def test_paired_interval_uses_t_distribution() -> None:
    mean, half = paired([10, 12, 14], [1, 2, 3])
    assert mean == pytest.approx(10.0)
    assert half == pytest.approx(t95(2) * 1.0 / math.sqrt(3))


def test_render_produces_one_row_per_policy_and_setting() -> None:
    results = run_settings([Setting("tiny", notice_s=60, sessions=40)], seeds=2,
                           policies=(Policy.RECOMPUTE, Policy.EVACUATE))
    table = render(results)
    assert table.count("| tiny |") == 2
    assert "± " in table
