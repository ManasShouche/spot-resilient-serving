import pytest

from kvevac.flush import flush_order

CHAINS = {
    "a": ["sys1", "sys2", "a1", "a2"],
    "b": ["sys1", "sys2", "b1"],
    "c": ["c1", "c2", "c3"],
}


def test_shared_prefix_blocks_ship_once() -> None:
    order = flush_order(["a", "b"], CHAINS, block_bytes=1, budget_bytes=100)
    assert order.keys == ["sys1", "sys2", "a1", "a2", "b1"]
    assert order.complete_sessions == ["a", "b"]


def test_budget_cut_leaves_a_usable_prefix_and_skips_the_rest() -> None:
    order = flush_order(["c", "a", "b"], CHAINS, block_bytes=10, budget_bytes=50)
    assert order.keys == ["c1", "c2", "c3", "sys1", "sys2"]
    assert order.complete_sessions == ["c"]
    assert order.partial_sessions == {"a": 2}
    assert order.skipped_sessions == ["b"]
    assert order.bytes_planned == 50


def test_blocks_already_at_destination_are_free() -> None:
    order = flush_order(["a"], CHAINS, block_bytes=10, budget_bytes=20,
                        already_present={"sys1", "sys2"})
    assert order.keys == ["a1", "a2"]
    assert order.complete_sessions == ["a"]


def test_prefix_order_is_never_violated() -> None:
    order = flush_order(["a", "b", "c"], CHAINS, block_bytes=1, budget_bytes=6)
    position = {key: i for i, key in enumerate(order.keys)}
    for chain in CHAINS.values():
        shipped = [position[k] for k in chain if k in position]
        assert shipped == sorted(shipped)


def test_rejects_nonpositive_block_size() -> None:
    with pytest.raises(ValueError):
        flush_order(["a"], CHAINS, block_bytes=0, budget_bytes=10)
