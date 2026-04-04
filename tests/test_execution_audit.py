from investing_bot.execution_audit import audit_execution_path, summarize_execution_audits


def test_execution_audit_detects_cancel_fill_race_and_slippage():
    intended = {"symbol": "SPY", "side": "buy", "order_type": "limit", "quantity": 1, "limit_price": 1.00}
    broker = {"symbol": "SPY", "side": "buy", "order_type": "limit", "quantity": 1, "limit_price": 1.00}
    lifecycle = [
        {"status": "submitted"},
        {"status": "cancelled"},
        {"status": "filled", "fill_quantity": 1, "fill_price": 1.02},
    ]

    audit = audit_execution_path(
        order_id="o-1",
        intended_spec=intended,
        broker_spec=broker,
        lifecycle_rows=lifecycle,
    )
    assert audit.race_detected
    assert audit.adverse_slippage_vs_limit == 0.02
    assert "cancel_fill_race_detected" in audit.reasons


def test_execution_audit_summary_aggregates_counts():
    audits = [
        audit_execution_path(
            order_id="o-1",
            intended_spec={"symbol": "SPY", "side": "buy", "order_type": "limit", "quantity": 1, "limit_price": 1.0},
            broker_spec={"symbol": "SPY", "side": "buy", "order_type": "limit", "quantity": 1, "limit_price": 1.0},
            lifecycle_rows=[{"status": "filled", "fill_quantity": 1, "fill_price": 1.0}],
        ),
        audit_execution_path(
            order_id="o-2",
            intended_spec={"symbol": "SPY", "side": "sell", "order_type": "limit", "quantity": 1, "limit_price": 1.0},
            broker_spec={"symbol": "QQQ", "side": "sell", "order_type": "limit", "quantity": 1, "limit_price": 1.0},
            lifecycle_rows=[{"status": "rejected"}],
        ),
    ]

    summary = summarize_execution_audits(audits)
    assert summary.order_count == 2
    assert summary.mismatch_count >= 1
    assert 0.0 <= summary.fill_rate <= 1.0
