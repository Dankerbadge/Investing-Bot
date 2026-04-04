from investing_bot.calibration import brier_score, quantile_pinball_loss, reliability_bins, summarize_fill_calibration


def test_brier_score_matches_expected_value():
    score = brier_score(
        predictions=[0.9, 0.2, 0.7, 0.1],
        outcomes=[1.0, 0.0, 1.0, 0.0],
    )
    assert abs(score - 0.0375) < 1e-12


def test_quantile_pinball_loss_matches_expected_value():
    loss = quantile_pinball_loss(
        predictions=[1.0, 2.0],
        actuals=[2.0, 1.0],
        quantile=0.8,
    )
    assert abs(loss - 0.5) < 1e-12


def test_reliability_bins_bucket_counts():
    bins = reliability_bins(
        predictions=[0.10, 0.15, 0.85, 0.90],
        outcomes=[0.0, 1.0, 1.0, 1.0],
        n_bins=5,
    )
    assert len(bins) == 5
    assert sum(item.count for item in bins) == 4
    assert bins[0].count == 2
    assert bins[4].count == 2
    assert abs(bins[0].empirical_rate - 0.5) < 1e-12


def test_summarize_fill_calibration_accepts_boolean_outcomes():
    summary = summarize_fill_calibration(
        [
            {"predicted_fill_probability": "0.8", "filled": True},
            {"predicted_fill_probability": 0.2, "filled": False},
            {"predicted_fill_probability": 0.6, "filled": True},
        ],
        n_bins=5,
    )

    assert summary["count"] == 3
    assert 0.0 <= summary["brier_score"] <= 1.0
    assert len(summary["reliability_bins"]) == 5
