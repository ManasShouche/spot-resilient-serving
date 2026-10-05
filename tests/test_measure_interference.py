import contextlib

import pytest

from kvevac.measure.interference import measure_interference
from tests.test_measure_prefill import FakeVLLM, server  # noqa: F401  (fixture reuse)


def test_slowdown_is_relative_to_idle_and_load_runs_per_rate(server, monkeypatch) -> None:  # noqa: F811
    started: list[float] = []

    @contextlib.contextmanager
    def fake_load(rate: float):
        started.append(rate)
        # Slow the fake server while "loaded" by shrinking its prefill throughput.
        monkeypatch.setattr("tests.test_measure_prefill.PREFILL_TOK_S", 100_000.0)
        yield {"achieved_gbps": rate}
        monkeypatch.setattr("tests.test_measure_prefill.PREFILL_TOK_S", 200_000.0)

    result = measure_interference(server, "fake", context=20_000, repeats=3,
                                  rates=[2.5], start_load=fake_load)
    idle, loaded = result["rows"]
    assert started == [2.5]
    assert idle["slowdown"] == 0.0
    assert loaded["slowdown"] == pytest.approx(1.0, abs=0.35)
    assert loaded["load"] == {"achieved_gbps": 2.5}
    assert loaded["load_failed"] is False


def test_rows_are_flagged_when_the_load_generator_reports_nothing(server) -> None:  # noqa: F811
    @contextlib.contextmanager
    def dead_load(rate: float):
        yield {}

    result = measure_interference(server, "fake", context=2_000, repeats=1, rates=[1.0],
                                  start_load=dead_load)
    assert result["rows"][1]["load_failed"] is True
