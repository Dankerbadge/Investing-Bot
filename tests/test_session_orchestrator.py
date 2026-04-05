from datetime import datetime

from investing_bot.preflight import PreflightResult
from investing_bot.session_orchestrator import SessionOrchestrator, determine_session_phase
from investing_bot.stream_manager import StreamSubscriptionManager


def _ok_preflight() -> PreflightResult:
    return PreflightResult(
        can_trade=True,
        hard_blocks=(),
        warnings=(),
        quote_age_p95_ms=300,
        stream_gap_p99_seconds=0.5,
        order_budget_utilization=0.2,
    )


def test_determine_session_phase_transitions():
    assert determine_session_phase(datetime(2026, 4, 6, 9, 10)) == "pre_open"
    assert determine_session_phase(datetime(2026, 4, 6, 9, 25)) == "warmup"
    assert determine_session_phase(datetime(2026, 4, 6, 10, 0)) == "active"
    assert determine_session_phase(datetime(2026, 4, 6, 15, 40)) == "de_risk"
    assert determine_session_phase(datetime(2026, 4, 6, 16, 10)) == "closed"


def test_session_orchestrator_blocks_entries_when_preflight_fails():
    manager = StreamSubscriptionManager()
    orchestrator = SessionOrchestrator(stream_manager=manager)

    preflight = PreflightResult(
        can_trade=False,
        hard_blocks=("quote_age_p95_exceeded",),
        warnings=(),
        quote_age_p95_ms=2200,
        stream_gap_p99_seconds=1.0,
        order_budget_utilization=0.2,
    )

    plan = orchestrator.plan(
        now_et=datetime(2026, 4, 6, 10, 0),
        desired_symbols_by_stream={"option_quotes": ["SPY", "QQQ"]},
        preflight=preflight,
    )

    assert plan.phase == "active"
    assert not plan.can_open_new_entries
    assert "quote_age_p95_exceeded" in plan.reasons
    assert any(action.action == "subscribe" for action in plan.stream_actions)


def test_session_orchestrator_de_risk_phase_prevents_new_entries():
    manager = StreamSubscriptionManager()
    orchestrator = SessionOrchestrator(stream_manager=manager)

    plan = orchestrator.plan(
        now_et=datetime(2026, 4, 6, 15, 40),
        desired_symbols_by_stream={"option_quotes": ["SPY"]},
        preflight=_ok_preflight(),
    )

    assert plan.phase == "de_risk"
    assert not plan.can_open_new_entries
    assert "de_risk_phase" in plan.reasons
