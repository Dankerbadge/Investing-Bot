import json

from investing_bot.experiment_registry import ExperimentRegistry, stable_hash, stamp_decision_context


def test_stable_hash_is_order_invariant_for_dicts():
    left = stable_hash({"a": 1, "b": 2})
    right = stable_hash({"b": 2, "a": 1})
    assert left == right


def test_stamp_decision_context_adds_policy_and_hashes():
    stamped = stamp_decision_context(
        decision_payload={"candidate_key": "SPY-TEST", "action": "passive_touch"},
        policy_version="policy-v3",
        config={"alpha": 1, "beta": 2},
        features={"feature_b": 2, "feature_a": 1},
    )
    assert stamped["policy_version"] == "policy-v3"
    assert "config_hash" in stamped
    assert "feature_hash" in stamped
    assert stamped["feature_keys"] == ["feature_a", "feature_b"]


def test_experiment_registry_records_decisions(tmp_path):
    registry = ExperimentRegistry(root_dir=tmp_path / "archive")
    path = registry.record_decision(
        decision_payload={"candidate_key": "SPY-TEST", "action": "skip"},
        policy_version="policy-v4",
        config={"foo": "bar"},
        features={"x": 1},
        source="live",
    )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["candidate_key"] == "SPY-TEST"
    assert row["action"] == "skip"
    assert row["policy_version"] == "policy-v4"
    assert row["data_source"] == "live"
