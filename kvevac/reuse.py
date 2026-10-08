"""Estimates of whether an idle session's cached context will be needed again.

The planner weighs each object by P(reuse). Three estimators bracket what prediction
could contribute:

- fixed:   one constant for every session (no information).
- recency: P(return | idle for t). A session ends after any turn with probability
           q = 1/70 (published median of 70 requests per session). Otherwise the next
           gap is lognormal with the published AgentX quantiles (p50 2.1 s, p90 51.1 s).
           By Bayes, P(return | idle t) = (1-q)S(t) / ((1-q)S(t) + q), where S is the
           survival function of the gap distribution.
- hinted:  a stand-in for metadata-driven predictors (CacheWise's tool-call features,
           Continuum's tool-duration TTLs, KVFlow's step graph). With probability
           `accuracy` it returns the oracle answer; otherwise it falls back to recency.
           Sweeping accuracy asks how good such a predictor must be to matter, without
           claiming the predictor itself (docs/positioning.md, section 4.4).
- oracle:  1 if the session really has another turn, else 0 (upper bound).
"""

from __future__ import annotations

import math
from enum import StrEnum

GAP_MEDIAN_S = 2.1
GAP_P90_S = 51.1
SESSION_END_PROB = 1 / 70


class ReuseModel(StrEnum):
    FIXED = "fixed"
    RECENCY = "recency"
    HINTED = "hinted"
    ORACLE = "oracle"


def _gap_survival(idle_s: float) -> float:
    if idle_s <= 0:
        return 1.0
    mu = math.log(GAP_MEDIAN_S)
    sigma = math.log(GAP_P90_S / GAP_MEDIAN_S) / 1.2816
    return 0.5 * math.erfc((math.log(idle_s) - mu) / (sigma * math.sqrt(2)))


def recency_reuse_prob(idle_s: float, end_prob: float = SESSION_END_PROB) -> float:
    survive = (1 - end_prob) * _gap_survival(idle_s)
    return survive / (survive + end_prob)


def hinted_reuse_prob(*, returns: bool, idle_s: float, accuracy: float, key: str) -> float:
    """Oracle answer with probability `accuracy` (decided by a stable hash of `key`, so
    every policy sees the same hints), else the recency estimate."""
    value = 2166136261
    for byte in key.encode():
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    if value / 2**32 < accuracy:
        return 1.0 if returns else 0.0
    return recency_reuse_prob(idle_s)
