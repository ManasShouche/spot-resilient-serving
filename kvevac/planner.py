"""Deadline-bounded evacuation planning.

When a node receives a termination notice of W seconds, it holds KV objects: idle
session prefix caches and the KV of in-flight requests. The node can (a) let an
in-flight request finish locally if its remaining decode fits in W, (b) ship an
object's KV to a destination outside the reclaim wave, or (c) drop it, leaving the
object to be recomputed later. The egress link is a single serial resource, so this is
a deadline-constrained knapsack with release times. The value of saving an object is
the expected recompute time it avoids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from itertools import combinations

from kvevac.costmodel import recompute_s, transfer_s
from kvevac.profiles import GpuProfile, LinkProfile, ModelProfile

FINISH_MARGIN_S = 1.0  # ASSUMED: slack kept between local completion and termination


class Action(StrEnum):
    FINISH_LOCAL = "finish_local"
    TRANSFER = "transfer"
    DROP = "drop"


@dataclass(frozen=True)
class KVObject:
    id: str
    tokens: int
    reuse_prob: float = 1.0
    """Probability the context is needed again (1.0 for an in-flight request)."""
    in_flight: bool = False
    remaining_decode_s: float = 0.0
    remaining_decode_tokens: int = 0
    session_reuse_prob: float = 0.9
    """For an in-flight request: probability its session sends another turn."""


@dataclass(frozen=True)
class Destination:
    id: str
    failure_group: str
    free_tokens: int
    link: LinkProfile
    survival_prob: float = 1.0
    remote_store: bool = False
    """A remote store must be fetched back on reuse; a peer serves the KV locally."""


@dataclass(frozen=True)
class Step:
    object_id: str
    action: Action
    destination: str | None = None
    start_s: float = 0.0
    end_s: float = 0.0
    value_s: float = 0.0


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    dest_ready_s: dict[str, float] = field(default_factory=dict)
    """Per destination: seconds from notice until its inbound link is free again."""

    @property
    def value_s(self) -> float:
        return sum(step.value_s for step in self.steps)

    def action_for(self, object_id: str) -> Step:
        return next(step for step in self.steps if step.object_id == object_id)


def save_value_s(obj: KVObject, dest: Destination, model: ModelProfile,
                 gpu: GpuProfile) -> float:
    """Expected recompute seconds avoided by placing obj's KV at dest."""
    reload = transfer_s(obj.tokens, model, dest.link) if dest.remote_store else 0.0
    gain = recompute_s(obj.tokens, gpu) - reload
    return max(0.0, obj.reuse_prob * dest.survival_prob * gain)


def _eligible(dests: list[Destination], source_group: str,
              doomed_groups: frozenset[str]) -> list[Destination]:
    blocked = doomed_groups | {source_group}
    return [d for d in dests if d.failure_group not in blocked and d.survival_prob > 0]


def plan_evacuation(
    objects: list[KVObject],
    destinations: list[Destination],
    *,
    notice_s: float,
    model: ModelProfile,
    gpu: GpuProfile,
    source_group: str,
    doomed_groups: frozenset[str] = frozenset(),
    dest_ready_s: dict[str, float] | None = None,
) -> Plan:
    """Greedy by value density on one serial egress pipe, respecting release times.

    `dest_ready_s` gives, per destination, how long its inbound link is already booked
    by other sources' evacuations; transfers to it cannot start earlier.
    """
    plan = Plan(dest_ready_s=dict(dest_ready_s or {}))
    free = {d.id: d.free_tokens for d in destinations}
    dests = _eligible(destinations, source_group, doomed_groups)

    # In-flight requests that can finish locally do so; their context is then
    # released for shipping once decoding completes.
    candidates: list[tuple[KVObject, float]] = []  # (object, release time)
    for obj in objects:
        if obj.in_flight and obj.remaining_decode_s + FINISH_MARGIN_S <= notice_s:
            plan.steps.append(Step(obj.id, Action.FINISH_LOCAL, end_s=obj.remaining_decode_s,
                                   value_s=recompute_s(obj.tokens, gpu)))
            done = KVObject(f"{obj.id}:session", obj.tokens + obj.remaining_decode_tokens,
                            reuse_prob=obj.session_reuse_prob)
            candidates.append((done, obj.remaining_decode_s))
        else:
            candidates.append((obj, 0.0))

    # Order objects by their best achievable value density, then place each on the
    # destination that maximizes value among those that can still finish before the
    # deadline (ties broken by earliest finish). The source's egress is one serial pipe;
    # each destination's ingress is shared with other sources via dest_ready_s.
    def density(item: tuple[KVObject, float]) -> float:
        obj = item[0]
        rates = [save_value_s(obj, d, model, gpu) / transfer_s(obj.tokens, model, d.link)
                 for d in dests]
        return max(rates, default=0.0)

    clock = 0.0
    for obj, release in sorted(candidates, key=density, reverse=True):
        best: tuple[float, float, Destination, float, float] | None = None
        for dest in dests:
            if free[dest.id] < obj.tokens:
                continue
            value = save_value_s(obj, dest, model, gpu)
            duration = transfer_s(obj.tokens, model, dest.link)
            start = max(clock, release, plan.dest_ready_s.get(dest.id, 0.0))
            if value <= 0 or start + duration > notice_s:
                continue
            key = (value, -(start + duration))
            if best is None or key > (best[0], -best[4]):
                best = (value, start, dest, duration, start + duration)
        if best is None:
            plan.steps.append(Step(obj.id, Action.DROP))
            continue
        value, start, dest, _, end = best
        clock = end
        plan.dest_ready_s[dest.id] = end
        free[dest.id] -= obj.tokens
        plan.steps.append(Step(obj.id, Action.TRANSFER, dest.id, start, end, value))
    return plan


def exact_value_single_destination(
    objects: list[KVObject], dest: Destination, *, notice_s: float, model: ModelProfile,
    gpu: GpuProfile,
) -> float:
    """Brute-force optimum for idle objects to one destination (test oracle, n <= 12)."""
    best = 0.0
    items = [(save_value_s(o, dest, model, gpu), transfer_s(o.tokens, model, dest.link),
              o.tokens) for o in objects]
    for size in range(1, len(items) + 1):
        for subset in combinations(items, size):
            if sum(i[1] for i in subset) <= notice_s and sum(i[2] for i in subset) <= \
                    dest.free_tokens:
                best = max(best, sum(i[0] for i in subset))
    return best
