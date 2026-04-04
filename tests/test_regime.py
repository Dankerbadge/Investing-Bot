from investing_bot.regime import infer_regime_context, regime_penalty, regime_reasons


def test_regime_context_penalizes_high_vol_and_thin_liquidity():
    regime = infer_regime_context(
        {
            "vix_level": 32,
            "put_call_ratio": 1.4,
            "macro_regime": "release",
            "spread_cost": 0.06,
        }
    )
    assert regime.risk_multiplier < 1.0
    assert regime_penalty(regime) > 0.0
    reasons = regime_reasons(regime)
    assert "regime_high_volatility" in reasons
    assert "regime_liquidity_thin" in reasons
