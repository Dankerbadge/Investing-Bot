from investing_bot.alpha_registry import build_default_alpha_registry


def _feature_rows():
    return [
        {
            "symbol": "SPY",
            "underlying": "SPY",
            "sec_recent_filing": True,
            "filing_shock_score": 0.50,
            "iv_minus_realized": 0.04,
            "model_confidence": 0.80,
            "liquidity_score": 0.90,
            "spread_cost": 0.01,
            "hedge_cost": 0.005,
            "stale_quote_penalty": 0.001,
            "event_gap_penalty": 0.001,
            "capital_lockup_penalty": 0.001,
            "fill_probability": 0.70,
            "convergence_probability": 0.60,
            "book_depth_contracts": 200,
            "quote_age_seconds": 0.5,
            "payoff_multiple": 1.2,
            "loss_multiple": 1.0,
            "reference_price": 1.0,
            "event_key": "filing:spy",
        },
        {
            "symbol": "QQQ",
            "underlying": "QQQ",
            "hours_since_event": 2,
            "post_event_iv_ratio": 1.25,
            "mean_reversion_score": 0.50,
            "model_confidence": 0.75,
            "liquidity_score": 0.85,
            "spread_cost": 0.01,
            "hedge_cost": 0.005,
            "stale_quote_penalty": 0.001,
            "event_gap_penalty": 0.001,
            "capital_lockup_penalty": 0.001,
            "fill_probability": 0.68,
            "convergence_probability": 0.58,
            "book_depth_contracts": 180,
            "quote_age_seconds": 0.6,
            "payoff_multiple": 1.15,
            "loss_multiple": 1.0,
            "reference_price": 1.1,
            "event_key": "post_event:qqq",
        },
        {
            "symbol": "IWM",
            "underlying": "IWM",
            "minutes_from_open": 8,
            "opening_drive_score": 0.60,
            "drive_direction": -1,
            "model_confidence": 0.70,
            "book_depth_contracts": 120,
            "liquidity_score": 0.80,
            "spread_cost": 0.01,
            "hedge_cost": 0.005,
            "stale_quote_penalty": 0.001,
            "event_gap_penalty": 0.001,
            "capital_lockup_penalty": 0.001,
            "fill_probability": 0.66,
            "convergence_probability": 0.57,
            "quote_age_seconds": 0.9,
            "payoff_multiple": 1.1,
            "loss_multiple": 1.0,
            "reference_price": 0.9,
            "event_key": "open_drive:iwm",
        },
    ]


def test_default_registry_builds_and_emits_signals():
    registry = build_default_alpha_registry()
    rows = _feature_rows()

    signals = registry.evaluate_all(rows)
    assert len(signals) == 3
    families = {signal.family for signal in signals}
    assert families == {"filing_vol", "post_event_iv", "open_drive"}


def test_signals_convert_to_candidates_with_feature_context():
    registry = build_default_alpha_registry()
    rows = _feature_rows()
    signals = registry.evaluate_all(rows)

    feature_index = {row["symbol"]: row for row in rows}
    candidates = registry.signals_to_candidates(signals, feature_index=feature_index)

    assert len(candidates) == 3
    symbols = {candidate.ticker for candidate in candidates}
    assert symbols == {"SPY", "QQQ", "IWM"}
    assert all(candidate.metadata["alpha_family"] in {"filing_vol", "post_event_iv", "open_drive"} for candidate in candidates)
    assert all(candidate.reference_price > 0 for candidate in candidates)


def test_registry_can_gate_families_on_broker_confirmed_live_evidence():
    registry = build_default_alpha_registry()
    rows = _feature_rows()

    signals = registry.evaluate_all(
        rows,
        live_evidence_by_family={"post_event_iv": 45, "filing_vol": 10, "open_drive": 0},
        min_broker_confirmed_live_samples=30,
    )
    assert len(signals) == 1
    assert signals[0].family == "post_event_iv"


def test_shadow_lane_keeps_learning_without_live_evidence():
    registry = build_default_alpha_registry()
    rows = _feature_rows()

    shadow_signals = registry.evaluate_shadow_all(rows)
    capital_signals = registry.evaluate_capital_eligible(
        rows,
        live_evidence_by_family={"post_event_iv": 35},
        min_broker_confirmed_live_samples=30,
    )

    assert len(shadow_signals) == 3
    assert len(capital_signals) == 1
    assert capital_signals[0].family == "post_event_iv"
