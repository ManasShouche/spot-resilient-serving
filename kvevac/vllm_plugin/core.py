"""vLLM-independent core of the deadline write-back prototype (docs/phase3-design.md).

Everything here is plain Python so it can be unit-tested without a GPU or a vLLM
install. `kvevac.vllm_plugin.manager` wires it into vLLM's tiering manager.

Pieces:
- CascadeMode: write_through (vLLM today), deferred (cascade only on notice) and
  hybrid (write-through while the tier keeps up; whatever backpressure drops is left
  dirty and flushed on notice).
- SessionIndex: which offload keys belong to which agent session, in prefix order,
  and which of them the secondary tier already holds.
- Control protocol: the notice handler (another process) asks the scheduler-side
  manager to flush by atomically writing a small JSON file; the manager polls it once
  per scheduler step and answers in a status file next to it.
- plan_flush: session priority (kvevac.planner over the sessions' real sizes and
  idle times) -> block order (kvevac.flush), truncated to what the tier can absorb
  before the deadline.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Hashable, Iterable
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from kvevac.costmodel import transfer_s
from kvevac.flush import FlushOrder, flush_order
from kvevac.planner import Action, Destination, KVObject, plan_evacuation, save_value_s
from kvevac.profiles import GPUS, GpuProfile, LinkProfile, ModelProfile
from kvevac.reuse import recency_reuse_prob

SESSION_PARAM = "kvevac_session_id"
"""Key in a request's kv_transfer_params naming its agent session. Clients send it as
`extra_body={"kv_transfer_params": {"kvevac_session_id": "..."}}`. Requests without
it are their own one-request session."""

DEADLINE_MARGIN_S = 2.0
"""ASSUMED: stop submitting this long before termination, so the last job can land."""


class CascadeMode(StrEnum):
    WRITE_THROUGH = "write_through"
    DEFERRED = "deferred"
    HYBRID = "hybrid"


@dataclass
class SessionChain:
    keys: dict[Hashable, int] = field(default_factory=dict)
    """Offload key -> end-token position (prefix order)."""
    last_used: float = 0.0
    requests: int = 0

    def ordered(self) -> list[Hashable]:
        return sorted(self.keys, key=self.keys.__getitem__)


class SessionIndex:
    """Which keys belong to which session, and which the secondary tier holds."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionChain] = {}
        self.cascaded: set[Hashable] = set()
        self.dirty: set[Hashable] = set()
        """Stored in the primary tier but never cascaded (deferred, or dropped by
        backpressure in hybrid mode)."""

    def record(self, session_id: str, key: Hashable, position: int | None,
               now: float) -> None:
        chain = self.sessions.setdefault(session_id, SessionChain())
        if position is None:  # unknown: append after everything we know of
            position = max(chain.keys.values(), default=-1) + 1
        chain.keys.setdefault(key, position)
        chain.last_used = max(chain.last_used, now)

    def touch(self, session_id: str, now: float) -> None:
        chain = self.sessions.setdefault(session_id, SessionChain())
        chain.last_used = max(chain.last_used, now)
        chain.requests += 1

    def mark_dirty(self, keys: Iterable[Hashable]) -> None:
        self.dirty.update(k for k in keys if k not in self.cascaded)

    def mark_cascaded(self, keys: Iterable[Hashable]) -> None:
        for key in keys:
            self.cascaded.add(key)
            self.dirty.discard(key)

    def uncascade(self, session_ids: Iterable[str]) -> None:
        """The tier lost these sessions' blocks (emptied on purpose): ship them again."""
        for sid in session_ids:
            chain = self.sessions.get(sid)
            if chain:
                self.cascaded.difference_update(chain.keys)
                self.dirty.update(chain.keys)

    def forget(self, keys: Iterable[Hashable]) -> None:
        """Keys evicted from the primary tier can no longer be flushed."""
        gone = set(keys)
        self.dirty -= gone
        for chain in self.sessions.values():
            for key in gone & chain.keys.keys():
                del chain.keys[key]


# ------------------------------------------------------------------ control protocol
@dataclass(frozen=True)
class FlushRequest:
    seq: int
    deadline_unix: float
    """Wall-clock termination time (the IMDS instance-action `time`)."""
    sessions: list[str] | None = None
    """Priority order chosen by the caller, or None to let plan_flush decide."""
    tier: int = 0
    only: list[str] | None = None
    """Restrict the flush to these sessions (None: every session the index knows)."""
    idle_s: dict[str, float] | None = None
    """Per-session idle time to plan with instead of the index's own clock. Lets a test
    replay a trace snapshot whose sessions were all prefilled moments ago."""
    tier_bytes_per_s: float | None = None
    """Write rate to plan with for this flush, if the link changed since startup."""
    reuse_p: dict[str, float] | None = None
    """Per-session P(reuse) to plan with instead of the recency estimate (e.g. from a
    learned predictor, kvevac.returnpred)."""
    reset: bool = False
    """Forget that the `only` sessions' blocks were already shipped (the caller emptied
    the tier), so the same resident KV can be flushed again under another policy."""


@dataclass
class FlushReport:
    seq: int
    started_unix: float
    sessions_planned: list[str]
    complete_sessions: list[str]
    partial_sessions: dict[str, int]
    skipped_sessions: list[str]
    keys_submitted: int
    bytes_submitted: int
    projected_finish_unix: float
    already_in_tier: int
    finished_unix: float | None = None
    keys_confirmed: int = 0
    segments: list[list] = field(default_factory=list)
    """[session, keys] runs in submission order, after dropping non-resident keys."""
    jobs_done: list[list] = field(default_factory=list)
    """[unix time, keys] for each flush store job as it was confirmed."""


def write_flush_request(path: Path, request: FlushRequest) -> None:
    """Atomic write: the manager may poll the file at any moment."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(request)))
    os.replace(tmp, path)


def read_flush_request(path: Path, last_seq: int) -> FlushRequest | None:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if int(raw.get("seq", 0)) <= last_seq:
        return None
    idle = raw.get("idle_s")
    return FlushRequest(seq=int(raw["seq"]), deadline_unix=float(raw["deadline_unix"]),
                        sessions=raw.get("sessions"), tier=int(raw.get("tier", 0)),
                        only=raw.get("only"),
                        idle_s={str(k): float(v) for k, v in idle.items()} if idle else None,
                        tier_bytes_per_s=float(raw["tier_bytes_per_s"])
                        if raw.get("tier_bytes_per_s") else None,
                        reuse_p={str(k): float(v) for k, v in raw["reuse_p"].items()}
                        if raw.get("reuse_p") else None,
                        reset=bool(raw.get("reset", False)))


def write_report(path: Path, report: FlushReport) -> None:
    status = path.with_suffix(path.suffix + ".status")
    tmp = status.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(report)))
    os.replace(tmp, status)


# ------------------------------------------------------------------------- planning
@dataclass(frozen=True)
class FlushParams:
    block_bytes: int
    block_tokens: int
    tier_bytes_per_s: float
    """Sustained write bandwidth of the target tier, measured in Phase 2."""
    tier_setup_s: float = 0.3
    gpu: GpuProfile = GPUS["l40s"]
    restore_bytes_per_s: float | None = None
    """Read-back rate on reuse, if it differs from the notice-time write rate."""


def plan_flush(index: SessionIndex, request: FlushRequest, params: FlushParams, *,
               now_unix: float | None = None) -> tuple[FlushOrder, list[str]]:
    """Session priority, then a prefix-ordered block list that fits before the deadline.

    Returns the block order and the session priority it was expanded from.
    """
    now = time.time() if now_unix is None else now_unix
    if request.tier_bytes_per_s:
        params = replace(params, tier_bytes_per_s=request.tier_bytes_per_s)
    window = max(0.0, request.deadline_unix - now - DEADLINE_MARGIN_S)
    budget = int(window * params.tier_bytes_per_s)
    allowed = set(request.only) if request.only is not None else None
    pending = {sid: chain.ordered() for sid, chain in index.sessions.items()
               if allowed is None or sid in allowed}
    order = request.sessions if request.sessions is not None else \
        session_priority(index, params, window, now, only=allowed, idle_s=request.idle_s,
                         reuse_p=request.reuse_p)
    if allowed is not None:
        order = [sid for sid in order if sid in allowed]
    flush = flush_order(order, pending, block_bytes=params.block_bytes,
                        budget_bytes=budget, already_present=index.cascaded)
    return flush, list(order)


def session_priority(index: SessionIndex, params: FlushParams, window_s: float,
                     now: float, *, only: set[str] | None = None,
                     idle_s: dict[str, float] | None = None,
                     reuse_p: dict[str, float] | None = None) -> list[str]:
    """Rank sessions for the flush: recompute avoided x P(reuse) per byte of tier
    bandwidth (kvevac.planner's value density).

    Two candidate orders, and the one worth more under this budget wins:
    - kvevac.planner's greedy plan: whole sessions that fit before the deadline, by
      density, then partial prefixes in leftover time, then everything else;
    - pure density order, where the budget cuts the last session to a prefix. Greedy
      skips a valuable session that does not fit whole and may spend the budget on a
      worse one that does; shipping a long head of the valuable one can be worth more.
    """
    model = ModelProfile("vllm", max(1, params.block_bytes // params.block_tokens))
    link = LinkProfile("tier", params.tier_bytes_per_s, params.tier_setup_s)
    objects = []
    for sid, chain in index.sessions.items():
        if only is not None and sid not in only:
            continue
        missing = sum(1 for k in chain.keys if k not in index.cascaded)
        if missing == 0:
            continue
        idle = idle_s[sid] if idle_s and sid in idle_s else now - chain.last_used
        p = reuse_p[sid] if reuse_p and sid in reuse_p else recency_reuse_prob(idle)
        objects.append(KVObject(sid, missing * params.block_tokens, reuse_prob=p))
    reload = LinkProfile("restore", params.restore_bytes_per_s, params.tier_setup_s) \
        if params.restore_bytes_per_s else None
    dest = Destination("tier", "remote", 10**15, link, remote_store=True,
                       reload_link=reload)
    plan = plan_evacuation(objects, [dest], notice_s=window_s, model=model,
                           gpu=params.gpu, source_group="local", partial_prefix=True)
    moved = sorted((s for s in plan.steps if s.action is Action.TRANSFER),
                   key=lambda s: s.start_s)
    greedy = [s.object_id for s in moved] + \
        [s.object_id for s in plan.steps if s.action is not Action.TRANSFER]

    def density(obj: KVObject) -> float:
        return save_value_s(obj, dest, model, params.gpu) / transfer_s(obj.tokens, model, link)

    by_density = [o.id for o in sorted(objects, key=density, reverse=True)]
    sizes = {o.id: o for o in objects}

    def worth(order: list[str]) -> float:
        budget, value = int(window_s * params.tier_bytes_per_s), 0.0
        for sid in order:
            tokens = min(sizes[sid].tokens, budget // model.kv_bytes_per_token)
            if tokens <= 0:
                break
            value += save_value_s(replace(sizes[sid], tokens=tokens), dest, model,
                                  params.gpu)
            budget -= tokens * model.kv_bytes_per_token
        return value

    return by_density if worth(by_density) > worth(greedy) else greedy
