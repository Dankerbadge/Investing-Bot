from investing_bot.reconciliation import reconcile_order_lifecycle


def test_reconcile_order_lifecycle_merges_order_and_account_events():
    snapshot = reconcile_order_lifecycle(
        order_events=[
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:00Z",
                "status": "submitted",
                "requested_quantity": 10,
            },
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:05Z",
                "status": "replaced",
                "order_quantity": 10,
            },
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:12Z",
                "status": "filled",
                "fill_quantity": 6,
            },
        ],
        account_activity_events=[
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:15Z",
                "activity_type": "filled",
                "filled_quantity": 4,
            },
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:20Z",
                "activity_type": "complete",
            },
            {
                "quote_mode": "delayed",
                "event_time": "2026-04-04T10:01:00Z",
            },
        ],
    )

    assert snapshot.delayed_quotes_detected is True
    assert "OID-1" in snapshot.orders
    lifecycle = snapshot.orders["OID-1"]
    assert lifecycle.order_id == "OID-1"
    assert lifecycle.first_timestamp == "2026-04-04T10:00:00Z"
    assert lifecycle.last_timestamp == "2026-04-04T10:00:20Z"
    assert lifecycle.status_path[0] == "submitted"
    assert lifecycle.final_status == "complete"
    assert lifecycle.requested_quantity == 10
    assert lifecycle.filled_quantity == 10
    assert lifecycle.cancel_replace_count == 1
    assert lifecycle.rejected is False


def test_reconcile_order_lifecycle_handles_empty_inputs():
    snapshot = reconcile_order_lifecycle(order_events=[], account_activity_events=[])
    assert snapshot.orders == {}
    assert snapshot.delayed_quotes_detected is False
