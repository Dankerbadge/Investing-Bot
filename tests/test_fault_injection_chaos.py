from investing_bot.chaos_harness import run_chaos_suite
from investing_bot.fault_injection import (
    inject_delayed_quotes,
    inject_order_change_race,
    inject_request_burst,
    inject_stream_gap,
)


def _base_rows():
    return [
        {"timestamp": "2026-04-04T10:00:00Z", "order_id": "o-1", "status": "submitted"},
        {"timestamp": "2026-04-04T10:00:01Z", "order_id": "o-1", "status": "working"},
    ]


def test_fault_injection_helpers_mutate_expected_fields():
    rows = _base_rows()
    with_gap = inject_stream_gap(rows, gap_seconds=7.0, at_index=0)
    assert with_gap[1]["stream_gap_seconds"] >= 7.0

    delayed = inject_delayed_quotes(rows)
    assert all(row.get("quote_mode") == "delayed" for row in delayed)

    race = inject_order_change_race(rows, order_id="o-1")
    statuses = {row.get("status") for row in race}
    assert "cancelled" in statuses and "filled" in statuses

    burst = inject_request_burst(rows, burst_count=5)
    assert len(burst) == len(rows) + 5


def test_chaos_suite_reports_failures_against_validator():
    def validator(rows):
        reasons = []
        if any(str(row.get("quote_mode") or "").lower() == "delayed" for row in rows):
            reasons.append("delayed_quotes")
        if any(float(row.get("stream_gap_seconds") or 0.0) > 5.0 for row in rows):
            reasons.append("stream_gap")
        if len(rows) > 120:
            reasons.append("request_burst")
        return len(reasons) == 0, reasons

    result = run_chaos_suite(base_rows=_base_rows(), validator=validator)
    assert result.total_scenarios == 4
    assert result.failed_scenarios >= 1
