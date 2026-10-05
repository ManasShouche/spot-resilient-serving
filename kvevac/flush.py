"""From a session-level evacuation plan to a block-level flush order.

vLLM stores KV as fixed-size blocks keyed by chained hashes; a request can reuse a
cached prefix only up to the first missing block. The planner decides *which
sessions* to save and in what order; this module turns that into the ordered list of
block keys to cascade before the deadline, with three rules:

1. Prefix order within a session: block i is never shipped before blocks 0..i-1,
   since a tail without its head is worthless.
2. Shared blocks ship once: agent sessions often share a system-prompt prefix, and a
   block already queued (or already present at the destination) costs nothing.
3. A byte budget (notice x bandwidth minus overheads) truncates the list. If it is cut
   mid-session, the shipped head is still a usable partial prefix.

This is pure Python on purpose: Phase 3 feeds it vLLM block-hash chains and hands its
output to the tiering manager's store path (docs/phase3-design.md).
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlushOrder:
    keys: list[Hashable] = field(default_factory=list)
    """Block keys in the order they should be cascaded."""
    bytes_planned: int = 0
    complete_sessions: list[str] = field(default_factory=list)
    partial_sessions: dict[str, int] = field(default_factory=dict)
    """Session id -> number of leading blocks that will arrive (cut by the budget)."""
    skipped_sessions: list[str] = field(default_factory=list)


def flush_order(
    session_order: Iterable[str],
    chains: Mapping[str, Sequence[Hashable]],
    *,
    block_bytes: int,
    budget_bytes: int,
    already_present: Iterable[Hashable] = (),
) -> FlushOrder:
    """Expand sessions (in planner priority order) into a deduplicated, prefix-ordered,
    budget-truncated list of block keys."""
    if block_bytes <= 0:
        raise ValueError("block_bytes must be positive")
    queued: set[Hashable] = set(already_present)
    keys: list[Hashable] = []
    used = 0
    complete, skipped = [], []
    partial: dict[str, int] = {}
    budget_left = True
    for session_id in session_order:
        chain = chains.get(session_id, ())
        if not budget_left:
            skipped.append(session_id)
            continue
        usable = 0
        for key in chain:
            if key in queued:
                usable += 1
                continue
            if used + block_bytes > budget_bytes:
                budget_left = False
                break
            keys.append(key)
            queued.add(key)
            used += block_bytes
            usable += 1
        if usable == len(chain):
            complete.append(session_id)
        elif usable > 0:
            partial[session_id] = usable
        else:
            skipped.append(session_id)
    return FlushOrder(keys, used, complete, partial, skipped)
