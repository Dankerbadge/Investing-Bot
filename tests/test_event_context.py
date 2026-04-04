from investing_bot.event_context import (
    event_context_penalty,
    event_context_reasons,
    infer_event_context,
    sec_submissions_url,
)


def test_event_context_flags_filing_and_earnings_windows():
    context = infer_event_context(
        {
            "sec_material_filing": True,
            "is_earnings_window": True,
            "is_macro_release_window": False,
            "assignment_risk": 0.7,
        }
    )
    reasons = event_context_reasons(context)
    assert context.filing_shock is True
    assert context.earnings_window is True
    assert "event_filing_shock" in reasons
    assert event_context_penalty(context) > 0.0


def test_sec_submission_url_uses_zero_padded_cik():
    assert sec_submissions_url("320193").endswith("CIK0000320193.json")
