import pytest

from kvevac.profiles import GPUS, LINKS, MODELS
from kvevac.sim import FleetConfig, Policy, Reclaim, independent_reclaims, run
from kvevac.workload import synthetic_sessions

KW = dict(model=MODELS["llama-3.1-8b"], gpu=GPUS["l40s"], link=LINKS["25gbe"])
FLEET = FleetConfig()
NODES = [f"{g}-n{i}" for g in FLEET.groups for i in range(FLEET.nodes_per_group)]


@pytest.fixture(scope="module")
def workload():
    return synthetic_sessions(60, arrival_window_s=1800, seed=11)


def reclaims(notice: float):
    return independent_reclaims(NODES, rate_per_node_h=0.2, horizon_s=4 * 3600,
                                notice_s=notice, seed=5)


def test_without_reclaims_reactive_policies_are_identical(workload) -> None:
    results = {p: run(workload, [], p, fleet=FLEET, **KW).prefill_gpu_s
               for p in (Policy.RECOMPUTE, Policy.DRAIN_LOCAL, Policy.EVACUATE)}
    assert len(set(results.values())) == 1


def test_zero_notice_makes_evacuation_equal_to_recompute(workload) -> None:
    events = reclaims(0.0)
    a = run(workload, events, Policy.RECOMPUTE, fleet=FLEET, **KW)
    b = run(workload, events, Policy.EVACUATE, fleet=FLEET, **KW)
    assert a.summary() == b.summary()


def test_long_notice_evacuation_loses_less_than_recompute(workload) -> None:
    events = reclaims(120.0)
    base = run(workload, [], Policy.RECOMPUTE, fleet=FLEET, **KW).prefill_gpu_s
    recompute = run(workload, events, Policy.RECOMPUTE, fleet=FLEET, **KW)
    evacuate = run(workload, events, Policy.EVACUATE, fleet=FLEET, **KW)
    assert evacuate.prefill_gpu_s - base < recompute.prefill_gpu_s - base
    assert evacuate.notice_egress_bytes > 0
    assert evacuate.killed_turns <= recompute.killed_turns


def test_drain_with_long_notice_kills_no_turns(workload) -> None:
    events = [Reclaim(1200.0, ("az-a-n0", "az-a-n1"), 600.0)]
    assert run(workload, events, Policy.DRAIN_LOCAL, fleet=FLEET, **KW).killed_turns == 0


def test_replication_pays_steady_state_egress(workload) -> None:
    fleet = FleetConfig(replica_tokens=2_000_000)
    metrics = run(workload, [], Policy.REPLICATE, fleet=fleet, **KW)
    assert metrics.replication_egress_bytes > 0 and metrics.notice_egress_bytes == 0


def test_simulation_is_deterministic(workload) -> None:
    events = reclaims(30.0)
    first = run(workload, events, Policy.EVACUATE, fleet=FLEET, **KW).summary()
    assert first == run(workload, events, Policy.EVACUATE, fleet=FLEET, **KW).summary()


def test_hybrid_never_does_worse_than_replicate_on_killed_turns(workload) -> None:
    fleet = FleetConfig(replica_tokens=2_000_000)
    events = reclaims(120.0)
    replicate = run(workload, events, Policy.REPLICATE, fleet=fleet, **KW)
    hybrid = run(workload, events, Policy.HYBRID, fleet=fleet, **KW)
    assert hybrid.killed_turns <= replicate.killed_turns
    assert hybrid.notice_egress_bytes > 0


def test_contention_delays_turns_queued_behind_a_cold_rebuild(workload) -> None:
    events = reclaims(0.0)
    free = run(workload, events, Policy.RECOMPUTE, fleet=FleetConfig(contention=False), **KW)
    busy = run(workload, events, Policy.RECOMPUTE, fleet=FleetConfig(contention=True), **KW)
    assert busy.prefill_gpu_s == pytest.approx(free.prefill_gpu_s, rel=0.05)
    assert sum(busy.ttft_s) > sum(free.ttft_s)


def test_draining_sessions_fail_over_to_their_live_replica(workload) -> None:
    fleet = FleetConfig(replica_tokens=4_000_000)
    events = reclaims(120.0)
    drain = run(workload, events, Policy.DRAIN_LOCAL, fleet=fleet, **KW)
    hybrid = run(workload, events, Policy.HYBRID, fleet=fleet, **KW)
    assert hybrid.lost_tokens < drain.lost_tokens


def test_budget_ratio_is_recorded_per_reclaimed_node(workload) -> None:
    metrics = run(workload, reclaims(60.0), Policy.RECOMPUTE, fleet=FLEET, **KW)
    assert metrics.budget_ratios and all(r > 0 for r in metrics.budget_ratios)


def test_tight_replication_budget_drops_updates_and_loses_more(workload) -> None:
    events = reclaims(0.0)
    roomy = run(workload, events, Policy.REPLICATE,
                fleet=FleetConfig(replica_tokens=4_000_000), **KW)
    tight = run(workload, events, Policy.REPLICATE,
                fleet=FleetConfig(replica_tokens=4_000_000, replication_bytes_per_s=2e6), **KW)
    assert roomy.replication_drops == 0 < tight.replication_drops
    assert tight.lost_tokens >= roomy.lost_tokens


def test_killed_turn_restarts_where_its_kv_was_evacuated(workload) -> None:
    events = reclaims(20.0)
    evac = run(workload, events, Policy.EVACUATE, fleet=FLEET, **KW)
    drain = run(workload, events, Policy.DRAIN_LOCAL, fleet=FLEET, **KW)
    assert evac.lost_tokens <= drain.lost_tokens


def test_remote_replicas_delay_failover_turns() -> None:
    busy = synthetic_sessions(400, arrival_window_s=3600, seed=2)
    events = independent_reclaims(NODES, rate_per_node_h=0.3, horizon_s=4 * 3600,
                                  notice_s=0.0, seed=8)
    local = run(busy, events, Policy.REPLICATE,
                fleet=FleetConfig(replica_tokens=4_000_000), **KW)
    remote = run(busy, events, Policy.REPLICATE,
                 fleet=FleetConfig(replica_tokens=4_000_000,
                                   replica_restore_link=LINKS["object-store"]), **KW)
    assert remote.affected_turns > local.affected_turns
    assert sum(remote.added_latency_s) > sum(local.added_latency_s)


def test_ingress_slowdown_charges_receivers_of_evacuated_kv(workload) -> None:
    events = reclaims(120.0)
    free = run(workload, events, Policy.EVACUATE, fleet=FLEET, **KW)
    slowed = run(workload, events, Policy.EVACUATE,
                 fleet=FleetConfig(ingress_slowdown=1.0), **KW)
    assert slowed.prefill_gpu_s > free.prefill_gpu_s
