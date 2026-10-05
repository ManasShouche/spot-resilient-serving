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
