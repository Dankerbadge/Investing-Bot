from investing_bot.ruin_guard import compute_ruin_guard


def test_ruin_guard_pauses_on_stage_daily_stop():
    decision = compute_ruin_guard(
        drawdown_fraction=0.05,
        daily_pnl_fraction=-0.02,
        stage="probe",
    )
    assert decision.paused
    assert decision.kelly_multiplier == 0.0
    assert "daily_drawdown_stop" in decision.reasons


def test_ruin_guard_reduces_multiplier_on_vol_and_loss_streak():
    decision = compute_ruin_guard(
        drawdown_fraction=0.05,
        daily_pnl_fraction=0.0,
        realized_volatility=0.04,
        rolling_loss_streak=4,
        stage="scaled_2",
    )
    assert not decision.paused
    assert 0.0 < decision.kelly_multiplier < 1.0
    assert "realized_vol_soft" in decision.reasons
    assert "loss_streak_soft" in decision.reasons
