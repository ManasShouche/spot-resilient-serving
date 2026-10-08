import pytest

from kvevac.reuse import SESSION_END_PROB, recency_reuse_prob


def test_recently_active_sessions_are_likely_to_return() -> None:
    assert recency_reuse_prob(0.0) == pytest.approx(1 - SESSION_END_PROB)


def test_reuse_probability_decays_with_idle_time() -> None:
    probs = [recency_reuse_prob(t) for t in (1, 60, 600, 3600, 6 * 3600)]
    assert probs == sorted(probs, reverse=True)
    assert probs[-1] < 0.6 < probs[0]


def test_hinted_estimator_brackets_recency_and_oracle() -> None:
    from kvevac.reuse import hinted_reuse_prob, recency_reuse_prob
    assert hinted_reuse_prob(returns=True, idle_s=300, accuracy=1.0, key="a") == 1.0
    assert hinted_reuse_prob(returns=False, idle_s=300, accuracy=1.0, key="a") == 0.0
    assert hinted_reuse_prob(returns=True, idle_s=300, accuracy=0.0, key="a") == \
        recency_reuse_prob(300)
