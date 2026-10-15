from kvevac.returnpred import FEATURES, features, source_of
from kvevac.workload import Session, Turn


def test_features_use_only_history_up_to_the_snapshot() -> None:
    turns = tuple(Turn(offset_s=10.0 * i, input_tokens=1000 * (i + 1), output_tokens=50)
                  for i in range(6))
    s = Session("abc123456789-0007", 0.0, turns)
    early = features(s, turns_done=3, idle_s=5.0, age_s=40.0, tokens=3000)
    assert set(early) == set(FEATURES)
    assert early["turns_done"] == 3.0
    # Later turns must not change the features of an earlier snapshot.
    longer = Session(s.id, 0.0, turns + (Turn(1e6, 1, 1),))
    assert features(longer, 3, 5.0, 40.0, 3000) == early


def test_resampled_ids_group_by_source_session() -> None:
    assert source_of("abc123456789-0007") == source_of("abc123456789-1203") == "abc123456789"
