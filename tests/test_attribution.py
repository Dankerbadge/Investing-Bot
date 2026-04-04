from investing_bot.attribution import compute_counterfactual_attribution


def test_counterfactual_attribution_components():
    result = compute_counterfactual_attribution(
        actual_pnl=120.0,
        crossed_now_pnl=100.0,
        worked_passive_pnl=110.0,
        skipped_pnl=0.0,
        half_size_pnl=60.0,
    )

    assert result.execution_alpha == 20.0
    assert result.selection_alpha == 100.0
    assert result.sizing_alpha == 60.0
