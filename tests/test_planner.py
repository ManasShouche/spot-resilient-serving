import random

from kvevac.planner import (
    Action,
    Destination,
    KVObject,
    exact_value_single_destination,
    plan_evacuation,
)
from kvevac.profiles import GPUS, LINKS, MODELS

M, G, L = MODELS["llama-3.1-8b"], GPUS["l40s"], LINKS["25gbe"]


def peer(id_="p1", group="az-b", free=10_000_000, **kw) -> Destination:
    return Destination(id_, group, free, L, **kw)


def plan(objects, dests, notice=120.0, **kw):
    return plan_evacuation(objects, dests, notice_s=notice, model=M, gpu=G,
                           source_group="az-a", **kw)


def test_transfers_fit_within_the_notice() -> None:
    objects = [KVObject(f"s{i}", 150_000) for i in range(20)]
    result = plan(objects, [peer()], notice=30.0)
    transfers = [s for s in result.steps if s.action is Action.TRANSFER]
    assert transfers and all(s.end_s <= 30.0 for s in transfers)
    assert any(s.action is Action.DROP for s in result.steps)


def test_never_evacuates_into_source_or_doomed_groups() -> None:
    objects = [KVObject("s1", 100_000)]
    dests = [peer("same", "az-a"), peer("doomed", "az-c")]
    result = plan(objects, dests, doomed_groups=frozenset({"az-c"}))
    assert result.action_for("s1").action is Action.DROP


def test_in_flight_request_that_fits_finishes_locally_then_ships() -> None:
    obj = KVObject("r1", 50_000, in_flight=True, remaining_decode_s=10.0,
                   remaining_decode_tokens=500)
    result = plan([obj], [peer()])
    assert result.action_for("r1").action is Action.FINISH_LOCAL
    shipped = result.action_for("r1:session")
    assert shipped.action is Action.TRANSFER and shipped.start_s >= 10.0


def test_in_flight_request_that_cannot_finish_is_transferred() -> None:
    obj = KVObject("r1", 50_000, in_flight=True, remaining_decode_s=500.0)
    assert plan([obj], [peer()]).action_for("r1").action is Action.TRANSFER


def test_destination_capacity_is_respected() -> None:
    objects = [KVObject("a", 60_000), KVObject("b", 60_000)]
    result = plan(objects, [peer(free=100_000)])
    assert sum(s.action is Action.TRANSFER for s in result.steps) == 1


def test_remote_store_is_worth_less_than_a_peer() -> None:
    obj = KVObject("s1", 100_000)
    store = Destination("store", "store", 10**12, LINKS["object-store"], remote_store=True)
    result = plan([obj], [store, peer()])
    assert result.action_for("s1").destination == "p1"


def test_greedy_is_near_optimal_on_small_instances() -> None:
    rng = random.Random(0)
    dest = peer()
    worst = 1.0
    for _ in range(30):
        objects = [KVObject(f"s{i}", rng.randint(5_000, 250_000),
                            reuse_prob=rng.uniform(0.2, 1.0)) for i in range(8)]
        notice = rng.uniform(5, 60)
        greedy = plan(objects, [dest], notice=notice).value_s
        optimum = exact_value_single_destination(objects, dest, notice_s=notice, model=M,
                                                 gpu=G)
        if optimum > 0:
            worst = min(worst, greedy / optimum)
    assert worst >= 0.6
