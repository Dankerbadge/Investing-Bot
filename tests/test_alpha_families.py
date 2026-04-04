from investing_bot.alpha_families import (
    generate_filing_vol_signals,
    generate_open_drive_signals,
    generate_post_event_iv_signals,
)


def test_filing_vol_generator_requires_recent_filing_and_shock():
    rows = [
        {
            "symbol": "SPY",
            "sec_recent_filing": True,
            "filing_shock_score": 0.40,
            "iv_minus_realized": 0.05,
            "model_confidence": 0.8,
            "liquidity_score": 0.9,
        },
        {
            "symbol": "QQQ",
            "sec_recent_filing": False,
            "filing_shock_score": 0.10,
            "iv_minus_realized": 0.05,
        },
    ]
    signals = generate_filing_vol_signals(rows)
    assert len(signals) == 1
    assert signals[0].symbol == "SPY"
    assert signals[0].side == "sell"


def test_post_event_iv_generator_filters_by_event_window():
    rows = [
        {
            "symbol": "QQQ",
            "hours_since_event": 4,
            "post_event_iv_ratio": 1.2,
            "mean_reversion_score": 0.6,
            "model_confidence": 0.75,
            "liquidity_score": 0.85,
        },
        {
            "symbol": "IWM",
            "hours_since_event": 30,
            "post_event_iv_ratio": 1.3,
            "mean_reversion_score": 0.7,
        },
    ]
    signals = generate_post_event_iv_signals(rows)
    assert len(signals) == 1
    assert signals[0].symbol == "QQQ"
    assert signals[0].side == "sell"


def test_open_drive_generator_uses_direction_for_side():
    rows = [
        {
            "symbol": "IWM",
            "minutes_from_open": 10,
            "opening_drive_score": 0.60,
            "book_depth_contracts": 100,
            "spread_cost": 0.01,
            "drive_direction": -1,
            "model_confidence": 0.70,
        }
    ]
    signals = generate_open_drive_signals(rows)
    assert len(signals) == 1
    assert signals[0].symbol == "IWM"
    assert signals[0].side == "sell"
