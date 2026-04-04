from investing_bot.corp_actions import (
    assignment_risk_score,
    corporate_action_hard_block,
    corporate_action_penalty,
    corporate_action_reasons,
    infer_corporate_action_context,
)


def test_adjusted_option_is_hard_blocked():
    context = infer_corporate_action_context({"adjusted_option": True})
    assert corporate_action_hard_block(context)
    assert corporate_action_penalty(context) >= 0.02
    assert "adjusted_option_contract" in corporate_action_reasons(context)


def test_assignment_risk_increases_near_expiration_and_ex_dividend():
    context = infer_corporate_action_context(
        {
            "side": "sell",
            "is_american": True,
            "dte": 1,
            "ex_dividend_days": 0,
            "intrinsic_value": 1.2,
            "extrinsic_value": 0.01,
        }
    )
    score = assignment_risk_score(context)
    assert score >= 0.85
    assert corporate_action_hard_block(context)
    assert "assignment_risk_hard_limit" in corporate_action_reasons(context)
