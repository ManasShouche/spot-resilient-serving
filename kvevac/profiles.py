"""Hardware, model, and link profiles.

Every constant here is ASSUMED until replaced by a measurement (see
docs/calibration.md). Each value carries a short provenance note so results can be
traced back to the assumption that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    kv_bytes_per_token: int
    """Bytes of KV per token: 2 (K,V) * layers * kv_heads * head_dim * dtype bytes."""


@dataclass(frozen=True)
class GpuProfile:
    name: str
    prefill_tokens_per_s: float
    """Short-context prefill throughput for the paired model (tokens/s)."""
    attention_knee_tokens: float
    """Context length at which attention doubles per-token prefill cost.

    Prefill time is modeled as c / p * (1 + c / (2 * knee)), i.e. the per-token cost
    grows linearly with context because attention is quadratic in c.
    """
    decode_tokens_per_s: float
    """Per-request decode rate at typical batch size (tokens/s)."""


@dataclass(frozen=True)
class LinkProfile:
    name: str
    bytes_per_s: float
    """Effective (not line-rate) throughput for KV transfer."""
    setup_s: float
    """Fixed per-transfer overhead: connection, metadata, registration."""


def _kv_bytes(layers: int, kv_heads: int, head_dim: int, dtype_bytes: int = 2) -> int:
    return 2 * layers * kv_heads * head_dim * dtype_bytes


MODELS = {
    # Architecture from the published configs (GQA, bf16 KV).
    "llama-3.1-8b": ModelProfile("llama-3.1-8b", _kv_bytes(32, 8, 128)),
    "llama-3.1-70b": ModelProfile("llama-3.1-70b", _kv_bytes(80, 8, 128)),
}

GPUS = {
    # ASSUMED: order-of-magnitude prefill/decode rates for an 8B model; to be measured.
    "l4": GpuProfile("l4", prefill_tokens_per_s=4_000, attention_knee_tokens=32_000,
                     decode_tokens_per_s=30),
    "l40s": GpuProfile("l40s", prefill_tokens_per_s=10_000, attention_knee_tokens=32_000,
                       decode_tokens_per_s=60),
    "h100": GpuProfile("h100", prefill_tokens_per_s=25_000, attention_knee_tokens=32_000,
                       decode_tokens_per_s=100),
    # ASSUMED: a 70B model, tensor-parallel over 4xH100 (one serving node).
    "h100x4-70b": GpuProfile("h100x4-70b", prefill_tokens_per_s=9_000,
                             attention_knee_tokens=48_000, decode_tokens_per_s=45),
}

LINKS = {
    # ASSUMED: effective TCP throughput, roughly 80% of line rate.
    "10gbe": LinkProfile("10gbe", bytes_per_s=1.0e9, setup_s=0.3),
    "25gbe": LinkProfile("25gbe", bytes_per_s=2.5e9, setup_s=0.3),
    "100gbe": LinkProfile("100gbe", bytes_per_s=10e9, setup_s=0.2),
    # ASSUMED: object store in another failure domain (multi-stream S3-class).
    "object-store": LinkProfile("object-store", bytes_per_s=0.8e9, setup_s=0.5),
}
