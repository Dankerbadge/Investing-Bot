from investing_bot.report_cards import build_report_cards, summarize_report_cards


def _rows():
    return [
        {
            "recorded_at": "2026-04-04T10:00:00Z",
            "alpha_family": "post_event_iv",
            "evidence_universe": "post_event_iv_standard",
            "broker_confirmed": True,
            "realized_alpha_density": 0.010,
            "realized_pnl": 12,
            "filled": True,
            "slippage": 0.010,
            "modeled_slippage": 0.008,
            "prevailing_spread": 0.020,
        },
        {
            "recorded_at": "2026-04-04T11:00:00Z",
            "alpha_family": "post_event_iv",
            "evidence_universe": "post_event_iv_standard",
            "broker_confirmed": True,
            "realized_alpha_density": 0.012,
            "realized_pnl": 10,
            "filled": True,
            "slippage": 0.011,
            "modeled_slippage": 0.008,
            "prevailing_spread": 0.020,
        },
        {
            "recorded_at": "2026-04-04T11:30:00Z",
            "alpha_family": "open_drive",
            "evidence_universe": "open_drive_top_tier",
            "broker_confirmed": False,
            "realized_alpha_density": 0.500,
            "realized_pnl": 100,
            "filled": True,
        },
    ]


def test_report_cards_use_broker_confirmed_rows_for_metrics():
    bundle = build_report_cards(
        _rows(),
        as_of_date="2026-04-04",
        min_samples_for_promotion=2,
        min_lcb95_alpha_density=0.0,
        min_fill_rate=0.5,
        max_slippage_over_model_p75=0.25,
    )

    assert len(bundle.cards) == 2
    pe = next(row for row in bundle.cards if row.alpha_family == "post_event_iv")
    assert pe.broker_confirmed_samples == 2
    assert pe.promotion_ready
    assert pe.status == "promote_candidate"

    od = next(row for row in bundle.cards if row.alpha_family == "open_drive")
    assert od.broker_confirmed_samples == 0
    assert od.status == "no_broker_evidence"


def test_report_card_summary_reports_top_candidates():
    bundle = build_report_cards(
        _rows(),
        as_of_date="2026-04-04",
        min_samples_for_promotion=2,
        min_lcb95_alpha_density=0.0,
    )
    summary = summarize_report_cards(bundle)

    assert summary["total_cards"] == 2
    assert summary["status_counts"]["promote_candidate"] >= 1
    assert len(summary["top_promote_candidates"]) >= 1
