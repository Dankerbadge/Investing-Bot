from investing_bot.evidence_pool import build_evidence_pool, capped_live_metric


def test_evidence_pool_shadow_lane_uses_hierarchical_shrinkage():
    pool = build_evidence_pool(
        [
            {"alpha_family": "post_event_iv", "evidence_universe": "post_event_iv_standard", "metric": 0.020, "sample_count": 100},
            {"alpha_family": "post_event_iv", "evidence_universe": "post_event_iv_weekly", "metric": 0.010, "sample_count": 80},
            {"alpha_family": "filing_vol", "evidence_universe": "filing_vol_8k", "metric": 0.005, "sample_count": 70},
        ]
    )

    estimate = pool.estimate(
        alpha_family="post_event_iv",
        evidence_universe="post_event_iv_standard",
        local_metric=0.0,
        local_samples=0,
        lane="shadow",
    )

    assert estimate.pooled_metric > 0
    assert estimate.universe_mean >= estimate.family_mean >= estimate.global_mean


def test_evidence_pool_capital_lane_never_boosts_above_local():
    pool = build_evidence_pool(
        [
            {"alpha_family": "post_event_iv", "evidence_universe": "post_event_iv_standard", "metric": 0.03, "sample_count": 120},
            {"alpha_family": "post_event_iv", "evidence_universe": "post_event_iv_weekly", "metric": 0.02, "sample_count": 90},
        ]
    )

    estimate = pool.estimate(
        alpha_family="post_event_iv",
        evidence_universe="post_event_iv_standard",
        local_metric=0.01,
        local_samples=40,
        lane="capital",
    )

    assert estimate.pooled_metric <= 0.01
    assert capped_live_metric(0.01, estimate.pooled_metric) == estimate.pooled_metric


def test_evidence_pool_capital_lane_with_no_local_samples_returns_zero():
    pool = build_evidence_pool(
        [{"alpha_family": "open_drive", "evidence_universe": "open_drive_top_tier", "metric": 0.02, "sample_count": 30}]
    )

    estimate = pool.estimate(
        alpha_family="open_drive",
        evidence_universe="open_drive_top_tier",
        local_metric=0.0,
        local_samples=0,
        lane="capital",
    )

    assert estimate.pooled_metric == 0.0
