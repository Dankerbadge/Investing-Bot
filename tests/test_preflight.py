from datetime import datetime, timezone

from investing_bot.preflight import run_preflight_checks
from investing_bot.reconciliation import BrokerTruthSnapshot


def _snapshot(**kwargs):
    defaults = dict(
        orders={},
        delayed_quotes_detected=False,
        duplicate_client_order_ids=(),
        duplicate_order_signatures=(),
        observed_requests_per_minute=20.0,
        request_budget_per_minute=120.0,
        request_budget_utilization=0.20,
        request_budget_breached=False,
    )
    defaults.update(kwargs)
    return BrokerTruthSnapshot(**defaults)


def test_preflight_blocks_on_delayed_quotes_and_duplicate_orders():
    snapshot = _snapshot(
        delayed_quotes_detected=True,
        duplicate_client_order_ids=("A",),
        request_budget_utilization=0.9,
    )
    result = run_preflight_checks(
        quote_rows=[{"quote_age_ms": 500, "stream_gap_seconds": 0.5}],
        broker_truth_snapshot=snapshot,
        now_utc=datetime(2026, 4, 4, 14, 0, tzinfo=timezone.utc),
    )

    assert not result.can_trade
    assert "broker_delayed_quotes_detected" in result.hard_blocks
    assert "duplicate_client_order_ids" in result.hard_blocks
    assert "order_budget_hard_exceeded" in result.hard_blocks


def test_preflight_uses_quote_timestamps_when_age_not_provided():
    now = datetime(2026, 4, 4, 14, 0, tzinfo=timezone.utc)
    quote_ts = int((now.timestamp() - 0.4) * 1000)
    result = run_preflight_checks(
        quote_rows=[{"QUOTE_TIME_MILLIS": quote_ts, "stream_gap_seconds": 0.2}],
        broker_truth_snapshot=_snapshot(),
        now_utc=now,
    )

    assert result.can_trade
    assert result.quote_age_p95_ms > 0
    assert result.stream_gap_p99_seconds == 0.2
