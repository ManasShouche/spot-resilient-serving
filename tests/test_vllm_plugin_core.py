from kvevac.vllm_plugin.core import (
    FlushParams,
    FlushRequest,
    SessionIndex,
    plan_flush,
    read_flush_request,
    write_flush_request,
)

BLOCK_TOKENS = 256
PARAMS = FlushParams(block_bytes=BLOCK_TOKENS * 131072, block_tokens=BLOCK_TOKENS,
                     tier_bytes_per_s=1e9, tier_setup_s=0.0)


def index_with(sessions: dict[str, int], *, idle: dict[str, float], now: float) -> SessionIndex:
    index = SessionIndex()
    for sid, blocks in sessions.items():
        for i in range(blocks):
            index.record(sid, f"{sid}-{i}", i * BLOCK_TOKENS, now - idle.get(sid, 0.0))
        index.mark_dirty(f"{sid}-{i}" for i in range(blocks))
    return index


def test_flush_ships_prefixes_in_order_within_the_deadline_budget() -> None:
    now = 1000.0
    index = index_with({"a": 40, "b": 40}, idle={"a": 1.0, "b": 1.0}, now=now)
    # 10 s window minus the 2 s margin at 1 GB/s: 8 GB, about 238 blocks of 33.5 MB.
    request = FlushRequest(seq=1, deadline_unix=now + 10.0, sessions=["b", "a"])
    flush, order = plan_flush(index, request, PARAMS, now_unix=now)
    assert order == ["b", "a"]
    assert flush.keys[:40] == [f"b-{i}" for i in range(40)]
    assert flush.bytes_planned <= 8e9


def test_flush_skips_blocks_already_in_the_tier_and_respects_a_short_deadline() -> None:
    now = 1000.0
    index = index_with({"a": 10}, idle={}, now=now)
    index.mark_cascaded(["a-0", "a-1"])
    flush, _ = plan_flush(index, FlushRequest(1, now + 2.5, ["a"]), PARAMS, now_unix=now)
    assert "a-0" not in flush.keys and len(flush.keys) <= 15  # 0.5 s of budget
    flush, _ = plan_flush(index, FlushRequest(2, now + 1.0, ["a"]), PARAMS, now_unix=now)
    assert flush.keys == []


def test_auto_priority_prefers_recent_sessions() -> None:
    now = 10_000.0
    index = index_with({"old": 20, "fresh": 20}, idle={"old": 3000.0, "fresh": 2.0},
                       now=now)
    _, order = plan_flush(index, FlushRequest(1, now + 5.0), PARAMS, now_unix=now)
    assert order[0] == "fresh"


def test_evicted_keys_are_forgotten() -> None:
    index = index_with({"a": 3}, idle={}, now=0.0)
    index.forget(["a-1"])
    assert index.sessions["a"].ordered() == ["a-0", "a-2"] and "a-1" not in index.dirty


def test_control_file_round_trip_ignores_stale_sequence_numbers(tmp_path) -> None:
    path = tmp_path / "flush.json"
    write_flush_request(path, FlushRequest(seq=7, deadline_unix=123.0, sessions=["s"]))
    assert read_flush_request(path, last_seq=0) == FlushRequest(7, 123.0, ["s"], 0)
    assert read_flush_request(path, last_seq=7) is None
    assert read_flush_request(tmp_path / "missing.json", last_seq=0) is None
