from kvevac.workload import CONTEXT_CAP, quantile, synthetic_sessions


def test_synthetic_sessions_match_published_agentx_marginals() -> None:
    sessions = synthetic_sessions(300, arrival_window_s=3600, seed=0)
    inputs = [t.input_tokens for s in sessions for t in s.turns]
    outputs = [t.output_tokens for s in sessions for t in s.turns]
    gaps = [
        b.offset_s - a.offset_s
        for s in sessions
        for a, b in zip(s.turns, s.turns[1:], strict=False)
    ]
    # Published: input p50 88.8k / p90 204k; output p50 376; gap p50 2.1 s.
    assert 65_000 <= quantile(inputs, 0.5) <= 115_000
    assert 160_000 <= quantile(inputs, 0.9) <= CONTEXT_CAP
    assert 300 <= quantile(outputs, 0.5) <= 460
    assert 1.5 <= quantile(gaps, 0.5) <= 3.0
    assert max(inputs) <= CONTEXT_CAP


def test_synthetic_sessions_are_deterministic_per_seed() -> None:
    assert synthetic_sessions(5, arrival_window_s=10, seed=3) == \
        synthetic_sessions(5, arrival_window_s=10, seed=3)


def test_agentx_loader_flattens_subagents_and_orders_turns(tmp_path) -> None:
    import json

    from kvevac.workload import load_agentx_jsonl

    row = {"id": "abc", "requests": [
        {"t": 5.0, "in": 2000, "out": 50, "hash_ids": [1, 2]},
        {"type": "subagent", "requests": [{"t": 2.0, "in": 1000, "out": 10, "hash_ids": [3]}]},
        {"t": 9.0, "in": 0, "out": 0},
    ]}
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps(row) + "\n")

    (session,) = load_agentx_jsonl(path, arrival_window_s=10)

    assert [t.offset_s for t in session.turns] == [0.0, 3.0]
    assert [t.input_tokens for t in session.turns] == [1000, 2000]
