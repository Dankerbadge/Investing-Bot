from investing_bot.reconciliation import reconcile_order_lifecycle, resolve_order_status


def test_reconcile_order_lifecycle_merges_order_and_account_events():
    snapshot = reconcile_order_lifecycle(
        order_events=[
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:00Z",
                "status": "submitted",
                "requested_quantity": 10,
                "client_order_id": "CID-1",
                "ticker": "SPY",
                "side": "sell",
                "limit_price": 1.05,
            },
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:05Z",
                "status": "replaced",
                "order_quantity": 10,
                "client_order_id": "CID-1",
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
        order_request_budget_per_minute=120.0,
    )

    assert snapshot.delayed_quotes_detected is True
    assert "OID-1" in snapshot.orders
    lifecycle = snapshot.orders["OID-1"]
    assert lifecycle.order_id == "OID-1"
    assert lifecycle.client_order_id == "CID-1"
    assert lifecycle.order_signature.startswith("SPY|sell|")
    assert lifecycle.first_timestamp == "2026-04-04T10:00:00Z"
    assert lifecycle.last_timestamp == "2026-04-04T10:00:20Z"
    assert lifecycle.status_path[0] == "submitted"
    assert lifecycle.final_status == "complete"
    assert lifecycle.requested_quantity == 10
    assert lifecycle.filled_quantity == 10
    assert lifecycle.cancel_replace_count == 1
    assert lifecycle.rejected is False
    assert snapshot.request_budget_per_minute == 120.0
    assert snapshot.request_budget_breached is False


def test_reconcile_order_lifecycle_handles_empty_inputs():
    snapshot = reconcile_order_lifecycle(order_events=[], account_activity_events=[])
    assert snapshot.orders == {}
    assert snapshot.delayed_quotes_detected is False


def test_reconcile_detects_duplicate_orders_and_budget_breach():
    order_events = []
    for index in range(125):
        order_events.append(
            {
                "order_id": f"OID-{index}",
                "client_order_id": "CID-DUP" if index in {0, 1} else f"CID-{index}",
                "ticker": "QQQ",
                "side": "buy",
                "limit_price": 1.11,
                "requested_quantity": 1,
                "timestamp": f"2026-04-04T10:00:{index % 60:02d}Z",
                "status": "submitted",
            }
        )
    snapshot = reconcile_order_lifecycle(
        order_events=order_events,
        account_activity_events=[],
        order_request_budget_per_minute=120.0,
    )

    assert "CID-DUP" in snapshot.duplicate_client_order_ids
    assert any(sig.startswith("QQQ|buy|") for sig in snapshot.duplicate_order_signatures)
    assert snapshot.observed_requests_per_minute > 120
    assert snapshot.request_budget_breached is True


def test_resolve_order_status_prefers_broker_truth():
    snapshot = reconcile_order_lifecycle(
        order_events=[
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:00Z",
                "status": "submitted",
                "requested_quantity": 1,
            },
            {
                "order_id": "OID-1",
                "timestamp": "2026-04-04T10:00:03Z",
                "status": "filled",
                "filled_quantity": 1,
            },
        ],
        account_activity_events=[],
    )

    truth = resolve_order_status(order_id="OID-1", local_status="working", snapshot=snapshot)
    assert truth.broker_confirmed is True
    assert truth.canonical_status == "filled"
    assert truth.pending_reconciliation is False
