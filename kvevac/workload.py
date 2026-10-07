"""Agentic multi-turn session workloads.

`synthetic_sessions` draws sessions whose marginals are calibrated to the published
summary of the SemiAnalysis AgentX corpus (393 Claude Code sessions, 68k requests) as
reported by github.com/gauravapiscean/agentic-kv-cache (results/02_characterize.txt):

    input tokens  p50 88,768   p90 204,288   max 255,808
    output tokens p50 376      p90 1,845
    inter-request gap p50 2.1 s   p90 51.1 s   p99 3,426 s
    requests/session p50 70    max 3,551

`load_agentx_jsonl` reads the real corpus (huggingface.co/datasets/semianalysisai/
cc-traces-weka-062126-256k, Apache-2.0) when it is available; the synthetic generator
is a stand-in, not a substitute, and results must say which one produced them.

The five generator parameters (starting context, per-turn growth, compaction target,
turns per session) were grid-fitted to the published input-token p50/p90; output
tokens and gaps use the published quantiles directly.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

CONTEXT_CAP = 256_000
COMPACT_TO = 10_000  # FITTED: context after an agent's compaction step


@dataclass(frozen=True)
class Turn:
    offset_s: float
    """Seconds after the session's first request."""
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Session:
    id: str
    start_s: float
    turns: tuple[Turn, ...]


def _lognormal(rng: random.Random, median: float, p90: float) -> float:
    sigma = math.log(p90 / median) / 1.2816
    return rng.lognormvariate(math.log(median), sigma)


def synthetic_sessions(
    n_sessions: int,
    *,
    arrival_window_s: float,
    seed: int = 0,
    max_turns: int = 400,
) -> list[Session]:
    rng = random.Random(seed)
    sessions = []
    for index in range(n_sessions):
        n_turns = max(1, min(max_turns, round(_lognormal(rng, 70, 200))))
        context = int(min(CONTEXT_CAP, _lognormal(rng, 6_000, 18_000)))
        offset = 0.0
        turns = []
        for _ in range(n_turns):
            output = max(1, round(_lognormal(rng, 376, 1_845)))
            turns.append(Turn(offset, context, output))
            delta = round(_lognormal(rng, 500, 3_000))
            context = context + output + delta
            if context > CONTEXT_CAP:
                context = COMPACT_TO
            offset += min(6 * 3600.0, _lognormal(rng, 2.1, 51.1))
        sessions.append(Session(f"s{index:04d}", rng.uniform(0, arrival_window_s),
                                tuple(turns)))
    return sessions


def load_agentx_jsonl(path: Path, *, arrival_window_s: float, seed: int = 0,
                      max_sessions: int | None = None) -> list[Session]:
    """Real AgentX corpus -> sessions. Start times are synthesized (the trace stores
    session-relative timestamps only), matching the reference replay harness."""
    rng = random.Random(seed)
    sessions = []
    with Path(path).open() as handle:
        for line in handle:
            raw = json.loads(line)
            requests = _flatten_requests(raw["requests"])
            if not requests:
                continue
            requests.sort(key=lambda item: item["t"])
            t0 = requests[0]["t"]
            turns = tuple(
                Turn(item["t"] - t0, int(item.get("in", 0)), int(item.get("out", 0)))
                for item in requests
            )
            sessions.append(Session(str(raw["id"]), rng.uniform(0, arrival_window_s), turns))
            if max_sessions and len(sessions) >= max_sessions:
                break
    return sessions


def resample_sessions(real: list[Session], n: int, *, arrival_window_s: float,
                      seed: int = 0) -> list[Session]:
    """`n` sessions drawn with replacement from real ones, each with a fresh id and start
    time. Keeps the offered load comparable to a synthetic run of `n` sessions when the
    corpus is smaller (AgentX has 393); every session's turns are real."""
    rng = random.Random(seed)
    out = []
    for index in range(n):
        source = rng.choice(real)
        out.append(Session(f"{source.id[:12]}-{index:04d}", rng.uniform(0, arrival_window_s),
                           source.turns))
    return out


def _flatten_requests(items: list[dict]) -> list[dict]:
    """Inline subagent requests; keep only requests that carry KV block hashes."""
    flat: list[dict] = []
    for item in items:
        if item.get("type") == "subagent":
            flat.extend(_flatten_requests(item.get("requests", [])))
        elif item.get("hash_ids"):
            flat.append(item)
    return flat


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]
