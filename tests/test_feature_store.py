from investing_bot.feature_store import FeatureStore, build_feature_payload


def test_build_feature_payload_merges_contexts_and_derives_fields():
    payload = build_feature_payload(
        sec_context={"sec_recent_filing": True},
        crowding_context={"cboe_put_call_ratio": 1.1},
        options_state={"book_depth_contracts": 120, "spread_cost": 0.02},
        equity_minute_context={"quote_age_ms": 500},
    )

    assert payload["sec_recent_filing"] is True
    assert payload["put_call_ratio"] == 1.1
    assert payload["liquidity_score"] > 0
    assert payload["quote_age_seconds"] == 0.5


def test_feature_store_latest_snapshot_respects_as_of_time():
    store = FeatureStore()
    store.add_snapshot(
        symbol="SPY",
        features={"spread_cost": 0.02},
        captured_at="2026-04-04T10:00:00Z",
    )
    store.add_snapshot(
        symbol="SPY",
        features={"spread_cost": 0.01},
        captured_at="2026-04-04T11:00:00Z",
    )

    early = store.get_feature_row("SPY", as_of="2026-04-04T10:30:00Z")
    late = store.get_feature_row("SPY", as_of="2026-04-04T11:30:00Z")

    assert early is not None
    assert late is not None
    assert early["spread_cost"] == 0.02
    assert late["spread_cost"] == 0.01


def test_feature_store_build_rows_and_prune():
    store = FeatureStore.from_rows(
        [
            {
                "symbol": "SPY",
                "captured_at": "2026-04-04T10:00:00Z",
                "spread_cost": 0.02,
            },
            {
                "symbol": "QQQ",
                "captured_at": "2026-04-04T10:05:00Z",
                "spread_cost": 0.03,
            },
        ]
    )

    rows = store.build_feature_rows(as_of="2026-04-04T10:10:00Z", max_age_seconds=120)
    assert len(rows) == 2
    assert any(row["symbol"] == "SPY" for row in rows)
    assert all("feature_is_stale" in row for row in rows)

    removed = store.prune_before("2026-04-04T10:03:00Z")
    assert removed == 1
    assert store.latest_snapshot("SPY") is None
    assert store.latest_snapshot("QQQ") is not None
