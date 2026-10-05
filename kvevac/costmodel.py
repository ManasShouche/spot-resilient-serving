"""Time to rebuild KV by recompute vs. by transfer, and where the two cross."""

from __future__ import annotations

from kvevac.profiles import GpuProfile, LinkProfile, ModelProfile

RECOMPUTE_SETUP_S = 0.2  # ASSUMED: scheduling + first-chunk latency


def recompute_s(tokens: int, gpu: GpuProfile) -> float:
    """Prefill time for `tokens` of context, with a linear attention penalty."""
    if tokens <= 0:
        return 0.0
    per_token = (1 + tokens / (2 * gpu.attention_knee_tokens)) / gpu.prefill_tokens_per_s
    return RECOMPUTE_SETUP_S + tokens * per_token


def kv_bytes(tokens: int, model: ModelProfile) -> int:
    return tokens * model.kv_bytes_per_token


def transfer_s(tokens: int, model: ModelProfile, link: LinkProfile) -> float:
    if tokens <= 0:
        return 0.0
    return link.setup_s + kv_bytes(tokens, model) / link.bytes_per_s


def cheaper_rebuild(tokens: int, model: ModelProfile, gpu: GpuProfile,
                    link: LinkProfile) -> str:
    return "transfer" if transfer_s(tokens, model, link) < recompute_s(tokens, gpu) else "recompute"


def crossover_tokens(model: ModelProfile, gpu: GpuProfile, link: LinkProfile,
                     max_tokens: int = 1_000_000) -> int | None:
    """Smallest context length at which transfer beats recompute, or None if never.

    Recompute is convex in tokens and transfer is affine, so once transfer wins it keeps
    winning; binary search is exact.
    """
    if cheaper_rebuild(max_tokens, model, gpu, link) == "recompute":
        return None
    lo, hi = 1, max_tokens
    while lo < hi:
        mid = (lo + hi) // 2
        if cheaper_rebuild(mid, model, gpu, link) == "transfer":
            hi = mid
        else:
            lo = mid + 1
    return lo
