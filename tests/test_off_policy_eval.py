from pathlib import Path

from investing_bot.experiment_registry import ExperimentRegistry
from investing_bot.off_policy_eval import (
    evaluate_challenger_dr,
    evaluate_challenger_ips,
    log_propensity,
    promotion_report,
)


def test_ips_and_dr_estimators_return_positive_signal_for_good_rows():
    rows = [
        {"realized_alpha_density": 0.010, "behavior_propensity": 0.40, "target_propensity": 0.60, "predicted_reward": 0.008},
        {"realized_alpha_density": 0.012, "behavior_propensity": 0.50, "target_propensity": 0.50, "predicted_reward": 0.009},
        {"realized_alpha_density": 0.011, "behavior_propensity": 0.45, "target_propensity": 0.55, "predicted_reward": 0.009},
        {"realized_alpha_density": 0.009, "behavior_propensity": 0.35, "target_propensity": 0.45, "predicted_reward": 0.008},
    ]
    ips = evaluate_challenger_ips(rows)
    dr = evaluate_challenger_dr(rows)

    assert ips.sample_count == 4
    assert dr.sample_count == 4
    assert ips.mean > 0
    assert dr.mean > 0


def test_log_propensity_writes_decision_row(tmp_path: Path):
    registry = ExperimentRegistry(root_dir=tmp_path)
    path = log_propensity(
        registry=registry,
        decision_payload={"candidate_key": "SPY-A", "action": "passive_touch"},
        policy_version="v1",
        config={"a": 1},
        features={"f": 2},
        behavior_propensity=0.4,
        target_propensity=0.6,
        predicted_reward=0.01,
        source="live",
    )

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "behavior_propensity" in text
    assert "target_propensity" in text


def test_promotion_report_requires_sample_and_positive_lcb():
    rows = [
        {"realized_alpha_density": 0.02, "behavior_propensity": 0.5, "target_propensity": 0.5, "predicted_reward": 0.015}
        for _ in range(40)
    ]
    ips = evaluate_challenger_ips(rows)
    dr = evaluate_challenger_dr(rows)

    report = promotion_report(
        champion="champion",
        challenger="challenger",
        ips=ips,
        doubly_robust=dr,
        min_effective_sample_size=10,
        min_lcb95=0.0,
    )
    assert report.promote
