"""Discrete-event simulation of agent sessions on a spot fleet under reclaim.

Model (v0, deliberately simple; see docs/simulator.md for what it leaves out):
- Sticky routing: a session's turns go to the node holding its prefix cache.
- A node's cache (GPU + host tier) holds whole-session prefixes, LRU over idle sessions.
- A turn prefills only the context beyond its resident prefix; incremental prefill is
  costed as recompute(context) - recompute(prefix).
- No queueing contention: each turn gets its own GPU time. GPU-seconds are reported so
  wasted work is visible even though latency ignores contention.
- Reclaims arrive with a notice of W seconds; the node is gone at notice + W and a
  replacement joins the same failure group after a delay with an empty cache.

Policies differ only in what they do between notice and termination (and, for
`replicate`, continuously before it):
- recompute:   no reaction; everything on the node is lost at termination.
- drain_local: stop admitting; in-flight turns that finish before the deadline do.
- evacuate:    drain_local + deadline-bounded KV evacuation (kvevac.planner).
- replicate:   continuous replication of each session cache to a peer in another
               failure group (pays steady-state egress); no action at notice.
- hybrid:      replicate, and at notice drain + evacuate only objects whose replica
               is missing or stale (in-flight turns, sessions not yet replicated).

Contention (FleetConfig.contention, default on): prefill is serialized per node, so a
cold rebuild delays every turn queued behind it; decode is treated as batched and
parallel. Time-to-first-token (TTFT) is recorded for every turn.
"""

from __future__ import annotations

import heapq
import itertools
import random
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import StrEnum

from kvevac.costmodel import kv_bytes, recompute_s, transfer_s
from kvevac.planner import Action, Destination, KVObject, plan_evacuation
from kvevac.profiles import GpuProfile, LinkProfile, ModelProfile
from kvevac.reuse import ReuseModel, recency_reuse_prob
from kvevac.workload import Session, quantile

REPLICATION_MAX_QUEUE_S = 5.0


class Policy(StrEnum):
    RECOMPUTE = "recompute"
    DRAIN_LOCAL = "drain_local"
    EVACUATE = "evacuate"
    REPLICATE = "replicate"
    HYBRID = "hybrid"
    """Continuous replication plus, at notice, evacuation of whatever replicas miss."""


@dataclass(frozen=True)
class Reclaim:
    at_s: float
    nodes: tuple[str, ...]
    notice_s: float


@dataclass(frozen=True)
class FleetConfig:
    groups: tuple[str, ...] = ("az-a", "az-b", "az-c")
    nodes_per_group: int = 4
    cache_tokens: int = 4_000_000
    """Per-node session-cache capacity (GPU KV + host DRAM tier), in tokens."""
    replica_tokens: int = 0
    """Per-node capacity of a separate replica tier (e.g. host DRAM/SSD). 0 means
    replicas share the primary cache and compete with live sessions for space."""
    replacement_delay_s: float = 300.0
    session_reuse_prob: float = 0.9
    """Used by ReuseModel.FIXED."""
    reuse_model: ReuseModel = ReuseModel.FIXED
    partial_prefix: bool = False
    ingress_slowdown: float = 0.0
    """Fractional prefill slowdown on a node while it receives evacuated KV (PCIe/NIC
    and host-memory contention). 0 means evacuation traffic is free for the receiver."""
    replica_restore_link: LinkProfile | None = None
    """If set, replicas live on remote capacity (e.g. vLLM's object-store tier) and a
    failover must first fetch the replica over this link. None: a peer's local tier,
    which restores without delay."""
    """Let the planner fill leftover notice time with partial session prefixes."""
    contention: bool = True
    replication_bytes_per_s: float | None = None
    """Per-node write-through budget. When the replication queue exceeds
    REPLICATION_MAX_QUEUE_S, the update is dropped and the replica goes stale (the
    shape of vLLM's ThrottledDropPolicy). None means unlimited bandwidth."""


@dataclass
class NodeState:
    id: str
    group: str
    alive: bool = True
    draining: bool = False
    cache: OrderedDict[str, int] = field(default_factory=OrderedDict)
    """session id -> resident prefix tokens, in LRU order (oldest first)."""
    replicas: OrderedDict[str, int] = field(default_factory=OrderedDict)
    """Replica tier (only used when FleetConfig.replica_tokens > 0)."""
    in_flight: dict[str, tuple[float, int, int]] = field(default_factory=dict)
    """session id -> (finish time, context tokens, output tokens)."""
    prefill_free_at: float = 0.0
    ingress_free_at: float = 0.0
    replication_free_at: float = 0.0
    """When this node's inbound link is next free (shared by concurrent evacuations)."""

    def used(self) -> int:
        return sum(self.cache.values())


@dataclass
class Metrics:
    turns: int = 0
    prefill_gpu_s: float = 0.0
    lost_prefill_gpu_s: float = 0.0
    """Prefill GPU-seconds spent rebuilding context that a reclaim destroyed."""
    lost_tokens: int = 0
    killed_turns: int = 0
    affected_turns: int = 0
    added_latency_s: list[float] = field(default_factory=list)
    notice_egress_bytes: int = 0
    replication_egress_bytes: int = 0
    evacuated_sessions: int = 0
    ttft_s: list[float] = field(default_factory=list)
    input_tokens: int = 0
    prefilled_tokens: int = 0
    replication_drops: int = 0
    first_event_s: float = 0.0
    last_event_s: float = 0.0
    budget_ratios: list[float] = field(default_factory=list)
    """Per reclaimed node: notice x link bandwidth / KV bytes resident at notice."""

    nodes: int = 1

    def summary(self) -> dict[str, float]:
        latency = self.added_latency_s or [0.0]
        return {
            "turns": self.turns,
            "prefill_gpu_s": round(self.prefill_gpu_s, 1),
            "lost_prefill_gpu_s": round(self.lost_prefill_gpu_s, 1),
            "lost_tokens_M": round(self.lost_tokens / 1e6, 2),
            "killed_turns": self.killed_turns,
            "affected_turns": self.affected_turns,
            "added_latency_p50_s": round(quantile(latency, 0.5), 2),
            "added_latency_p99_s": round(quantile(latency, 0.99), 2),
            "notice_egress_GB": round(self.notice_egress_bytes / 1e9, 1),
            "replication_egress_GB": round(self.replication_egress_bytes / 1e9, 1),
            "evacuated_sessions": self.evacuated_sessions,
            "budget_ratio_mean": round(sum(self.budget_ratios) / max(1, len(self.budget_ratios)),
                                       2),
            "replication_drops": self.replication_drops,
            "replication_MBps_per_node": round(
                self.replication_egress_bytes / 1e6
                / max(1.0, self.last_event_s - self.first_event_s) / self.nodes, 2),
            "cache_hit_rate": round(1 - self.prefilled_tokens / max(1, self.input_tokens), 3),
            "ttft_mean_s": round(sum(self.ttft_s) / max(1, len(self.ttft_s)), 2),
            "ttft_p50_s": round(quantile(self.ttft_s or [0.0], 0.5), 2),
            "ttft_p99_s": round(quantile(self.ttft_s or [0.0], 0.99), 2),
        }


@dataclass
class SessionState:
    session: Session
    next_turn: int = 0
    node: str | None = None
    prefix_tokens: int = 0
    """Context that would be cached if nothing had been lost (session's true prefix)."""
    lost_by_reclaim: bool = False
    replica: str | None = None
    available_at: float = 0.0
    """Earliest time the session's (evacuated) cache is usable at its node."""
    last_active: float = 0.0


def independent_reclaims(node_ids: list[str], *, rate_per_node_h: float, horizon_s: float,
                         notice_s: float, seed: int) -> list[Reclaim]:
    rng = random.Random(seed)
    events = []
    for node in node_ids:
        t = rng.expovariate(rate_per_node_h / 3600)
        while t < horizon_s:
            events.append(Reclaim(t, (node,), notice_s))
            t += rng.expovariate(rate_per_node_h / 3600)
    return sorted(events, key=lambda e: e.at_s)


def correlated_reclaims(groups: dict[str, list[str]], *, bursts: int, horizon_s: float,
                        notice_s: float, fraction: float, seed: int) -> list[Reclaim]:
    """Each burst reclaims `fraction` of one failure group at once (SkyServe-style)."""
    rng = random.Random(seed)
    events = []
    for _ in range(bursts):
        group = rng.choice(sorted(groups))
        members = groups[group]
        k = max(1, round(fraction * len(members)))
        events.append(Reclaim(rng.uniform(0.1 * horizon_s, 0.9 * horizon_s),
                              tuple(rng.sample(members, k)), notice_s))
    return sorted(events, key=lambda e: e.at_s)


class Simulation:
    def __init__(self, sessions: list[Session], reclaims: list[Reclaim], *, policy: Policy,
                 fleet: FleetConfig, model: ModelProfile, gpu: GpuProfile,
                 link: LinkProfile, store: LinkProfile | None = None) -> None:
        self.policy = policy
        self.fleet = fleet
        self.model, self.gpu, self.link, self.store = model, gpu, link, store
        self.metrics = Metrics(nodes=len(fleet.groups) * fleet.nodes_per_group)
        self.nodes: dict[str, NodeState] = {}
        for group in fleet.groups:
            for index in range(fleet.nodes_per_group):
                node_id = f"{group}-n{index}"
                self.nodes[node_id] = NodeState(node_id, group)
        self.sessions = {s.id: SessionState(s) for s in sessions}
        self._seq = itertools.count()
        self._events: list[tuple[float, int, str, tuple]] = []
        self._replacements = itertools.count()
        for state in self.sessions.values():
            self._push(state.session.start_s, "turn", (state.session.id, None))
        for reclaim in reclaims:
            self._push(reclaim.at_s, "notice", (reclaim,))

    # ------------------------------------------------------------------ events
    def _push(self, at: float, kind: str, payload: tuple) -> None:
        heapq.heappush(self._events, (at, next(self._seq), kind, payload))

    def run(self) -> Metrics:
        if self._events:
            self.metrics.first_event_s = self._events[0][0]
        while self._events:
            now, _, kind, payload = heapq.heappop(self._events)
            self.metrics.last_event_s = now
            getattr(self, f"_on_{kind}")(now, *payload)
        return self.metrics

    # ----------------------------------------------------------------- routing
    def _live_nodes(self) -> list[NodeState]:
        return [n for n in self.nodes.values() if n.alive and not n.draining]

    def _pick_node(self, exclude_groups: set[str] = frozenset()) -> NodeState:
        live = [n for n in self._live_nodes() if n.group not in exclude_groups] or \
            self._live_nodes()
        return min(live, key=lambda n: (len(n.in_flight), n.used()))

    def _insert(self, node: NodeState, session_id: str, tokens: int) -> None:
        node.cache.pop(session_id, None)
        node.cache[session_id] = tokens
        while node.used() > self.fleet.cache_tokens:
            victim = next((s for s in node.cache if s not in node.in_flight and
                           s != session_id), None)
            if victim is None:
                break
            node.cache.pop(victim)

    # ------------------------------------------------------------------- turns
    def _on_turn(self, now: float, session_id: str, requested_at: float | None) -> None:
        state = self.sessions[session_id]
        requested = now if requested_at is None else requested_at
        if state.available_at > now:
            # The session's KV is still in transit to its new node: wait for it.
            self._push(state.available_at, "turn", (session_id, requested))
            return
        turn = state.session.turns[state.next_turn]
        node = self.nodes.get(state.node) if state.node else None
        if node is None or not node.alive or node.draining:
            replica = self._take_replica(session_id, now)
            if replica is not None:
                node = replica
                if state.available_at > now:
                    state.node = node.id
                    self._push(state.available_at, "turn", (session_id, requested))
                    return
            else:
                if node is not None and session_id in node.cache:
                    state.lost_by_reclaim = True  # its cache is on a node about to vanish
                node = self._pick_node()
            state.node = node.id
        start = now
        resident = min(node.cache.get(session_id, 0), turn.input_tokens)
        expected = min(state.prefix_tokens, turn.input_tokens)
        prefill = recompute_s(turn.input_tokens, self.gpu) - recompute_s(resident, self.gpu)
        if resident < expected and state.lost_by_reclaim:
            lost = recompute_s(expected, self.gpu) - recompute_s(resident, self.gpu)
            self.metrics.lost_prefill_gpu_s += lost
            self.metrics.lost_tokens += expected - resident
            self.metrics.affected_turns += 1
            self.metrics.added_latency_s.append(lost + (start - requested))
        elif start > requested:
            self.metrics.affected_turns += 1
            self.metrics.added_latency_s.append(start - requested)
        state.lost_by_reclaim = False
        self.metrics.turns += 1
        self.metrics.prefill_gpu_s += prefill
        self.metrics.input_tokens += turn.input_tokens
        self.metrics.prefilled_tokens += turn.input_tokens - resident
        if self.fleet.ingress_slowdown and start < node.ingress_free_at:
            extra = prefill * self.fleet.ingress_slowdown
            prefill += extra
            self.metrics.prefill_gpu_s += extra  # the GPU is busy longer: count it
        if self.fleet.contention:
            start = max(start, node.prefill_free_at)
            node.prefill_free_at = start + prefill
        self.metrics.ttft_s.append(start + prefill - requested)
        finish = start + prefill + turn.output_tokens / self.gpu.decode_tokens_per_s
        node.in_flight[session_id] = (finish, turn.input_tokens, turn.output_tokens)
        node.cache.move_to_end(session_id) if session_id in node.cache else None
        self._push(finish, "finish", (session_id, node.id))

    def _on_finish(self, now: float, session_id: str, node_id: str) -> None:
        node = self.nodes[node_id]
        if session_id not in node.in_flight:
            return  # killed by a reclaim and restarted elsewhere
        _, context, output = node.in_flight.pop(session_id)
        state = self.sessions[session_id]
        state.prefix_tokens = context + output
        state.last_active = now
        if node.alive:
            self._insert(node, session_id, context + output)
            if self.policy in (Policy.REPLICATE, Policy.HYBRID):
                self._replicate(now, node, state, context + output)
        state.next_turn += 1
        if state.next_turn < len(state.session.turns):
            turn = state.session.turns[state.next_turn]
            self._push(max(now, state.session.start_s + turn.offset_s), "turn",
                       (session_id, None))

    def _replicate(self, now: float, node: NodeState, state: SessionState,
                   tokens: int) -> None:
        replica = self.nodes.get(state.replica) if state.replica else None
        if replica is None or not replica.alive or replica.group == node.group:
            candidates = [n for n in self._live_nodes() if n.group != node.group]
            if not candidates:
                return
            replica = min(candidates, key=lambda n: n.used())
            shipped = tokens
        else:
            held = (replica.replicas if self.fleet.replica_tokens else replica.cache)
            shipped = max(0, tokens - held.get(state.session.id, 0))
        budget = self.fleet.replication_bytes_per_s
        if budget:
            if node.replication_free_at - now > REPLICATION_MAX_QUEUE_S:
                self.metrics.replication_drops += 1
                return  # dropped under backpressure: the replica stays stale
            start = max(now, node.replication_free_at)
            # Simplification: the replica is updated immediately, not at queue drain.
            node.replication_free_at = start + kv_bytes(shipped, self.model) / budget
        state.replica = replica.id
        if self.fleet.replica_tokens:
            replica.replicas.pop(state.session.id, None)
            replica.replicas[state.session.id] = tokens
            while sum(replica.replicas.values()) > self.fleet.replica_tokens:
                replica.replicas.popitem(last=False)
        else:
            self._insert(replica, state.session.id, tokens)
        self.metrics.replication_egress_bytes += kv_bytes(shipped, self.model)

    # ---------------------------------------------------------------- reclaims
    def _on_notice(self, now: float, reclaim: Reclaim) -> None:
        doomed = [self.nodes[n] for n in reclaim.nodes if self.nodes[n].alive]
        doomed_ids = {n.id for n in doomed}
        for node in doomed:
            self._push(now + reclaim.notice_s, "terminate", (node.id,))
            resident = kv_bytes(node.used(), self.model)
            if resident:
                self.metrics.budget_ratios.append(
                    reclaim.notice_s * self.link.bytes_per_s / resident)
            if self.policy in (Policy.RECOMPUTE, Policy.REPLICATE):
                continue
            node.draining = True
            if self.policy in (Policy.EVACUATE, Policy.HYBRID):
                self._evacuate(now, node, reclaim.notice_s, doomed_ids)

    def _evacuate(self, now: float, node: NodeState, notice_s: float,
                  doomed_ids: set[str]) -> None:
        objects = []
        for session_id, tokens in node.cache.items():
            if session_id in node.in_flight or self._replica_is_current(session_id, tokens,
                                                                         doomed_ids):
                continue
            objects.append(KVObject(session_id, tokens,
                                    reuse_prob=self._reuse_prob(session_id, now)))
        for session_id, (finish, context, output) in node.in_flight.items():
            remaining = max(0.0, finish - now)
            objects.append(KVObject(session_id, context, in_flight=True,
                                    remaining_decode_s=remaining,
                                    remaining_decode_tokens=output,
                                    session_reuse_prob=self._reuse_prob(session_id, now,
                                                                        in_flight=True)))
        destinations = [
            Destination(n.id, n.group, self.fleet.cache_tokens - n.used(), self.link)
            for n in self._live_nodes() if n.id not in doomed_ids
        ]
        if self.store is not None:
            destinations.append(Destination("store", "store", 10**12, self.store,
                                            remote_store=True))
        ready = {d.id: max(0.0, self.nodes[d.id].ingress_free_at - now)
                 for d in destinations if d.id in self.nodes}
        plan = plan_evacuation(objects, destinations, notice_s=notice_s, model=self.model,
                               gpu=self.gpu, source_group=node.group, dest_ready_s=ready,
                               partial_prefix=self.fleet.partial_prefix)
        for dest_id, free_after in plan.dest_ready_s.items():
            if dest_id in self.nodes:
                self.nodes[dest_id].ingress_free_at = now + free_after
        for step in plan.steps:
            if step.action is not Action.TRANSFER:
                continue
            session_id = step.object_id.removesuffix(":session")
            state = self.sessions[session_id]
            tokens = step.tokens
            self.metrics.notice_egress_bytes += kv_bytes(tokens, self.model)
            self.metrics.evacuated_sessions += 1
            if step.destination != "store":
                state.node = step.destination
                state.available_at = now + step.end_s
            self._push(now + step.end_s, "arrive", (session_id, step.destination, tokens))

    def _reuse_prob(self, session_id: str, now: float, in_flight: bool = False) -> float:
        state = self.sessions[session_id]
        model = self.fleet.reuse_model
        if model is ReuseModel.ORACLE:
            following = state.next_turn + 1 if in_flight else state.next_turn
            return 1.0 if following < len(state.session.turns) else 0.0
        if model is ReuseModel.RECENCY:
            return recency_reuse_prob(0.0 if in_flight else now - state.last_active)
        return self.fleet.session_reuse_prob

    def _take_replica(self, session_id: str, now: float) -> NodeState | None:
        """Fail a session over to its live replica, promoting the replica to primary."""
        if self.policy not in (Policy.REPLICATE, Policy.HYBRID):
            return None
        state = self.sessions[session_id]
        replica = self.nodes.get(state.replica) if state.replica else None
        if replica is None or not replica.alive or replica.draining:
            return None
        held = (replica.replicas.pop(session_id, 0) if self.fleet.replica_tokens
                else replica.cache.get(session_id, 0))
        if not held:
            return None
        self._insert(replica, session_id, held)
        state.replica = None
        state.lost_by_reclaim = False
        if self.fleet.replica_restore_link is not None:
            state.available_at = now + transfer_s(held, self.model,
                                                  self.fleet.replica_restore_link)
        return replica

    def _replica_is_current(self, session_id: str, tokens: int, doomed_ids: set[str]) -> bool:
        if self.policy is not Policy.HYBRID:
            return False
        replica_id = self.sessions[session_id].replica
        replica = self.nodes.get(replica_id) if replica_id else None
        if replica is None or not replica.alive or replica.id in doomed_ids:
            return False
        held = replica.replicas if self.fleet.replica_tokens else replica.cache
        return held.get(session_id, 0) >= tokens

    def _on_arrive(self, now: float, session_id: str, dest_id: str, tokens: int) -> None:
        state = self.sessions[session_id]
        if dest_id == "store":
            # Restore lands on whichever node the session is routed to next; charge the
            # fetch as a delay, which is cheaper than recompute by construction.
            target = self._pick_node()
            state.available_at = now + transfer_s(tokens, self.model, self.store)
        else:
            target = self.nodes[dest_id]
            if not target.alive:
                return
        if session_id in target.in_flight or not target.alive:
            return
        self._insert(target, session_id, tokens)
        state.node = target.id
        state.lost_by_reclaim = False

    def _on_terminate(self, now: float, node_id: str) -> None:
        node = self.nodes[node_id]
        node.alive = False
        for session_id in list(node.cache):
            state = self.sessions[session_id]
            if state.node == node_id:
                state.lost_by_reclaim = True
                state.node = None
                replica = self._take_replica(session_id, now)
                if replica is not None:
                    state.node = replica.id
        node.cache.clear()
        node.replicas.clear()
        for session_id, (_, context, _output) in list(node.in_flight.items()):
            # Output-preserving restart (ShuntServe-style): re-prefill prompt+partial output.
            del node.in_flight[session_id]
            self.metrics.killed_turns += 1
            state = self.sessions[session_id]
            state.lost_by_reclaim = True
            state.prefix_tokens = context
            if state.node == node_id:
                state.node = None  # else: its KV was evacuated; restart where it went
            self._push(now, "turn", (session_id, None))
        self._push(now + self.fleet.replacement_delay_s, "replace", (node.group,))

    def _on_replace(self, now: float, group: str) -> None:
        node_id = f"{group}-r{next(self._replacements)}"
        self.nodes[node_id] = NodeState(node_id, group)


def run(sessions: list[Session], reclaims: list[Reclaim], policy: Policy, **kwargs) -> Metrics:
    return Simulation(sessions, reclaims, policy=policy, **kwargs).run()
