from investing_bot.latency import build_latency_profile, estimate_latency_penalty, latency_kill_switch


def test_latency_profile_builds_from_timestamps():
    profile = build_latency_profile(
        {
            "decision_start": "2026-04-04T10:00:00Z",
            "decision_end": "2026-04-04T10:00:00.800000Z",
            "submit_time": "2026-04-04T10:00:01Z",
            "ack_time": "2026-04-04T10:00:02Z",
            "final_fill_time": "2026-04-04T10:00:04Z",
            "quote_age_seconds": 0.5,
        }
    )
    assert abs(profile.decision_ms - 800.0) < 0.1
    assert profile.submit_to_ack_ms == 1000.0
    assert profile.ack_to_fill_ms == 2000.0
    assert profile.stale_quote is False


def test_latency_kill_switch_flags_stale_conditions():
    profile = build_latency_profile({"quote_age_ms": 5000, "decision_ms": 1500, "submit_to_ack_ms": 6000})
    blocked, reasons = latency_kill_switch(profile)
    assert blocked is True
    assert "latency_quote_age_exceeded" in reasons
    assert "latency_decision_exceeded" in reasons
    assert "latency_submit_ack_exceeded" in reasons
    assert estimate_latency_penalty(profile) > 0.01
