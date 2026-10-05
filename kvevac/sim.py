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
from kvevac.workload import Session, quantile


class Policy(StrEnum):
    RECOMPUTE = "recompute"
    DRAIN_LOCAL = "drain_local"
    EVACUATE = "evacuate"
    REPLICATE = "replicate"


@dataclass(frozen=True)
class Reclaim:
    at_s: float
    nodes: tuple[str, ...]
    notice_s: float


@dataclass(frozen=True)
class FleetConfig:
    groups: tuple[str, ...] = ("az-a", "az-b", "az-c")
    nodes_per_group: int = 4
    cache_tokens: int = 2_000_000
    """Per-node session-cache capacity (GPU KV + host DRAM tier), in tokens."""
    replica_tokens: int = 0
    """Per-node capacity of a separate replica tier (e.g. host DRAM/SSD). 0 means
    replicas share the primary cache and compete with live sessions for space."""
    replacement_delay_s: float = 300.0
    session_reuse_prob: float = 0.9


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
        self.metrics = Metrics()
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
        while self._events:
            now, _, kind, payload = heapq.heappop(self._events)
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
        if node.alive:
            self._insert(node, session_id, context + output)
            if self.policy is Policy.REPLICATE:
                self._replicate(node, state, context + output)
        state.next_turn += 1
        if state.next_turn < len(state.session.turns):
            turn = state.session.turns[state.next_turn]
            self._push(max(now, state.session.start_s + turn.offset_s), "turn",
                       (session_id, None))

    def _replicate(self, node: NodeState, state: SessionState, tokens: int) -> None:
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
            if self.policy in (Policy.RECOMPUTE, Policy.REPLICATE):
                continue
            node.draining = True
            if self.policy is Policy.EVACUATE:
                self._evacuate(now, node, reclaim.notice_s, doomed_ids)

    def _evacuate(self, now: float, node: NodeState, notice_s: float,
                  doomed_ids: set[str]) -> None:
        objects = []
        for session_id, tokens in node.cache.items():
            if session_id in node.in_flight:
                continue
            objects.append(KVObject(session_id, tokens,
                                    reuse_prob=self.fleet.session_reuse_prob))
        for session_id, (finish, context, output) in node.in_flight.items():
            remaining = max(0.0, finish - now)
            objects.append(KVObject(session_id, context, in_flight=True,
                                    remaining_decode_s=remaining,
                                    remaining_decode_tokens=output,
                                    session_reuse_prob=self.fleet.session_reuse_prob))
        destinations = [
            Destination(n.id, n.group, self.fleet.cache_tokens - n.used(), self.link)
            for n in self._live_nodes() if n.id not in doomed_ids
        ]
        if self.store is not None:
            destinations.append(Destination("store", "store", 10**12, self.store,
                                            remote_store=True))
        plan = plan_evacuation(objects, destinations, notice_s=notice_s, model=self.model,
                               gpu=self.gpu, source_group=node.group)
        for step in plan.steps:
            if step.action is not Action.TRANSFER:
                continue
            session_id = step.object_id.removesuffix(":session")
            state = self.sessions[session_id]
            tokens = next(o.tokens for o in objects if o.id == step.object_id) if \
                not step.object_id.endswith(":session") else state.prefix_tokens
            self.metrics.notice_egress_bytes += kv_bytes(tokens, self.model)
            self.metrics.evacuated_sessions += 1
            if step.destination != "store":
                state.node = step.destination
                state.available_at = now + step.end_s
            self._push(now + step.end_s, "arrive", (session_id, step.destination, tokens))

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
                if self.policy is Policy.REPLICATE and state.replica:
                    replica = self.nodes[state.replica]
                    held = replica.replicas.get(session_id) if self.fleet.replica_tokens \
                        else replica.cache.get(session_id)
                    if replica.alive and held:
                        if self.fleet.replica_tokens:
                            replica.replicas.pop(session_id)
                            self._insert(replica, session_id, held)
                        state.node = replica.id
                        state.replica = None
                        state.lost_by_reclaim = False
        node.cache.clear()
        node.replicas.clear()
        for session_id, (_, context, _output) in list(node.in_flight.items()):
            # Output-preserving restart (ShuntServe-style): re-prefill prompt+partial output.
            del node.in_flight[session_id]
            self.metrics.killed_turns += 1
            state = self.sessions[session_id]
            state.lost_by_reclaim = True
            state.prefix_tokens = context
            state.node = None
            self._push(now, "turn", (session_id, None))
        self._push(now + self.fleet.replacement_delay_s, "replace", (node.group,))

    def _on_replace(self, now: float, group: str) -> None:
        node_id = f"{group}-r{next(self._replacements)}"
        self.nodes[node_id] = NodeState(node_id, group)


def run(sessions: list[Session], reclaims: list[Reclaim], policy: Policy, **kwargs) -> Metrics:
    return Simulation(sessions, reclaims, policy=policy, **kwargs).run()
