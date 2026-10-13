import argparse
import json
import time
from pathlib import Path

import pytest

from kvevac import planner_trials as pt
from kvevac.flush import flush_order
from kvevac.planner import Destination, KVObject, save_value_s
from kvevac.profiles import LinkProfile, ModelProfile
from kvevac.vllm_plugin.core import (
    FlushParams,
    FlushRequest,
    SessionIndex,
    plan_flush,
    read_flush_request,
    write_flush_request,
)

BLOCK_TOKENS = 256
KV = pt.KV_BYTES_PER_TOKEN
PARAMS = FlushParams(block_bytes=BLOCK_TOKENS * KV, block_tokens=BLOCK_TOKENS,
                     tier_bytes_per_s=1e9, tier_setup_s=0.0, gpu=pt.L40S_MEASURED,
                     restore_bytes_per_s=pt.RESTORE_BPS)


def index_with(blocks: dict[str, int], now: float) -> SessionIndex:
    index = SessionIndex()
    for sid, n in blocks.items():
        for i in range(n):
            index.record(sid, f"{sid}-{i}", i * BLOCK_TOKENS, now)
    return index


# ------------------------------------------------------------------ plugin protocol
def test_request_round_trips_new_fields(tmp_path: Path) -> None:
    path = tmp_path / "flush.json"
    req = FlushRequest(3, 9.0, ["a"], 0, only=["a", "b"], idle_s={"a": 4.0},
                       tier_bytes_per_s=2.5e8, reset=True)
    write_flush_request(path, req)
    assert read_flush_request(path, 0) == req


def test_only_restricts_the_flush_and_idle_override_drives_the_planner() -> None:
    now = 1000.0
    index = index_with({"old": 300, "x": 300, "y": 300}, now)
    # x looks long idle (unlikely to return), y just active: the planner ships y first.
    req = FlushRequest(1, now + 12.0, only=["x", "y"], idle_s={"x": 7200.0, "y": 1.0})
    flush, order = plan_flush(index, req, PARAMS, now_unix=now)
    assert order[0] == "y" and "old" not in order
    assert set(flush.key_sessions) <= {"x", "y"}
    assert flush.key_sessions[0] == "y"


def test_per_request_rate_sets_the_budget() -> None:
    now = 1000.0
    index = index_with({"a": 2000}, now)
    slow = FlushRequest(1, now + 12.0, ["a"], tier_bytes_per_s=2.5e8)
    flush, _ = plan_flush(index, slow, PARAMS, now_unix=now)
    assert len(flush.keys) * PARAMS.block_bytes <= 10 * 2.5e8


def test_reset_makes_shipped_blocks_flushable_again() -> None:
    now = 1000.0
    index = index_with({"a": 10}, now)
    index.mark_cascaded([f"a-{i}" for i in range(10)])
    flush, _ = plan_flush(index, FlushRequest(1, now + 30, ["a"]), PARAMS, now_unix=now)
    assert flush.keys == []
    index.uncascade(["a"])
    flush, _ = plan_flush(index, FlushRequest(2, now + 30, ["a"]), PARAMS, now_unix=now)
    assert len(flush.keys) == 10


def test_flush_order_records_each_keys_session() -> None:
    order = flush_order(["a", "b"], {"a": [1, 2], "b": [2, 3]}, block_bytes=1,
                        budget_bytes=10)
    assert order.keys == [1, 2, 3] and order.key_sessions == ["a", "a", "b"]


def test_reload_link_separates_restore_from_the_notice_link() -> None:
    model = ModelProfile("8b", KV)
    slow = LinkProfile("notice", 2.5e8, 0.0)
    fast = LinkProfile("restore", 1e12, 0.0)
    obj = KVObject("s", 60_000)
    same = Destination("d", "g", 10**9, slow, remote_store=True)
    split = Destination("d", "g", 10**9, slow, remote_store=True, reload_link=fast)
    assert save_value_s(obj, same, model, pt.L40S_MEASURED) == 0.0
    assert save_value_s(obj, split, model, pt.L40S_MEASURED) > 5.0


# ------------------------------------------------------------------- trial helpers
SESSIONS = {"s-0": {"tokens": 90_000, "idle_s": 30.0, "returns": True},
            "s-1": {"tokens": 20_000, "idle_s": 2.0, "returns": True},
            "s-2": {"tokens": 110_000, "idle_s": 9000.0, "returns": False}}


def test_baseline_orders() -> None:
    assert pt.baseline_order("planner", SESSIONS, "x") is None
    assert pt.baseline_order("recent", SESSIONS, "x") == ["s-1", "s-0", "s-2"]
    assert pt.baseline_order("largest", SESSIONS, "x") == ["s-2", "s-0", "s-1"]
    assert pt.baseline_order("oracle", SESSIONS, "x") == ["s-0", "s-1", "s-2"]
    assert sorted(pt.baseline_order("random", SESSIONS, "x")) == sorted(SESSIONS)
    with pytest.raises(ValueError):
        pt.baseline_order("lifo", SESSIONS, "x")


def test_saved_tokens_counts_only_jobs_confirmed_by_the_deadline() -> None:
    report = {"segments": [["a", 3], ["b", 4]],
              "jobs_done": [[10.0, 2], [11.0, 2], [12.5, 3]]}
    assert pt.saved_tokens(report, 11.0, 16) == {"a": 48, "b": 16}
    assert pt.saved_tokens(report, 20.0, 16) == {"a": 48, "b": 64}


def test_value_is_zero_where_restore_loses_to_recompute() -> None:
    # Measured L40S prefill vs. 0.9 GB/s restore cross over around 50-55k tokens.
    assert pt.session_value_s(20_000) == 0.0
    assert pt.session_value_s(100_000) > 5.0


# ------------------------------------------------------------- end to end, faked GPU
class FakeEngine:
    """Stands in for vLLM + the plugin: answers prompts, and on a wake request plans a
    pending flush with the real plan_flush and confirms it at the shaped link rate."""

    def __init__(self, control: Path, rate: float) -> None:
        self.control, self.rate = control, rate
        self.index, self.seq, self.cascaded_by = SessionIndex(), 0, {}

    def complete(self, port, model, prompt, session, max_tokens, timeout_s=0.0):
        if session != "wake":
            tokens = int(len(prompt.split()) / pt.WORDS_PER_TOKEN)
            now = time.time()
            for i in range(0, tokens, BLOCK_TOKENS):
                self.index.record(session, f"{session}-{i}", i, now)
            return {"ttft_s": 0.01, "text": "", "prompt_tokens": tokens, "total_s": 0.01}
        req = read_flush_request(self.control, self.seq)
        if req:
            self.seq = req.seq
            if req.reset and req.only:
                self.index.uncascade(req.only)
            started = time.time()
            flush, order = plan_flush(self.index, req, PARAMS, now_unix=started)
            self.index.mark_cascaded(flush.keys)
            segments, done, t = [], [], started
            for sid in flush.key_sessions:
                if segments and segments[-1][0] == sid:
                    segments[-1][1] += 1
                else:
                    segments.append([sid, 1])
            for _ in flush.keys:  # one key per job, at the request's link rate
                t += PARAMS.block_bytes / (req.tier_bytes_per_s or self.rate)
                done.append([t, 1])
            status = self.control.with_suffix(".json.status")
            status.write_text(json.dumps({
                "seq": req.seq, "started_unix": started, "finished_unix": started,
                "keys_submitted": len(flush.keys),
                "bytes_submitted": len(flush.keys) * PARAMS.block_bytes,
                "keys_confirmed": len(flush.keys), "projected_finish_unix": t,
                "sessions_planned": order, "segments": segments, "jobs_done": done}))
        return {"ttft_s": 0.0, "text": "", "prompt_tokens": 1, "total_s": 0.0}


def test_run_end_to_end_with_a_fake_engine(tmp_path: Path, monkeypatch) -> None:
    from kvevac.vllm_plugin import gpu_test

    spec = {"trials": [{"snapshot": 0, "sessions": list(SESSIONS.values())}]}
    (tmp_path / "trials.json").write_text(json.dumps(spec))
    out = tmp_path / "out"
    engine = FakeEngine(out / "flush.json", 4e10)

    class FakeServer:
        def __init__(self, *a, **k):
            self.proc = type("P", (), {"poll": lambda self: None})()

        def kill(self):
            pass

    monkeypatch.setattr(gpu_test, "Server", FakeServer)
    monkeypatch.setattr(gpu_test, "complete", engine.complete)
    monkeypatch.setattr(gpu_test, "write_bandwidth", lambda tier, gb=2: 4e10)
    monkeypatch.setattr(gpu_test, "text", lambda seed, words: "w " * words)
    monkeypatch.setattr(pt, "throttle", lambda iface, rate: None)
    monkeypatch.setattr(pt, "SETTLE_S", 0.0)
    real_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda s: real_sleep(min(s, 0.01)))
    args = argparse.Namespace(trials=tmp_path / "trials.json", tier=tmp_path / "tier",
                              out=out, model="m", cpu_gb=1.0, max_snapshots=1,
                              python="python", logs=tmp_path, notices=[2.3],
                              links=[40000.0], iface="eth0", max_minutes=5.0)
    # 2.3 s notice - 2 s margin at a (fake) 40 GB/s: 12 GB of ~29 GB resident.
    pt.run(args)
    result = json.loads((out / "planner_trials.json").read_text())
    assert {t["policy"] for t in result["trials"]} == set(pt.POLICIES)
    by_policy = {t["policy"]: t for t in result["trials"]}
    # Oracle and planner both start with the returning 90k session; largest wastes the
    # budget on the session that never returns.
    assert next(iter(by_policy["oracle"]["saved_tokens"])) == "s0-0"
    assert next(iter(by_policy["planner"]["saved_tokens"])) == "s0-0"
    assert next(iter(by_policy["largest"]["saved_tokens"])) == "s0-2"
    scored = pt.score(result)
    rows = {r["policy"]: r for r in scored["rows"]}
    assert rows["largest"]["value_s"] == 0.0
    # Same choice; the planner's budget can differ by a block (it plans a moment later).
    assert rows["oracle"]["value_s"] > 0
    assert rows["planner"]["value_s"] == pytest.approx(rows["oracle"]["value_s"], abs=0.2)
    assert rows["recent"]["value_s"] < rows["planner"]["value_s"]
    assert 0.3 < rows["planner"]["rho"] < 0.5


def test_priority_ships_a_head_of_the_valuable_session_over_a_worse_whole_one() -> None:
    # 13 GB of budget. The just-active 120k session does not fit whole; greedy would
    # spend the budget on the 90k session idle for 25 min. Its long head is worth more.
    now = 1000.0
    index = index_with({"busy": 120_000 // BLOCK_TOKENS, "stale": 90_000 // BLOCK_TOKENS},
                       now)
    req = FlushRequest(1, now + 15.0, idle_s={"busy": 2.6, "stale": 1500.0})
    flush, order = plan_flush(index, req, PARAMS, now_unix=now)
    assert order[0] == "busy"
    assert set(flush.key_sessions) == {"busy"}
