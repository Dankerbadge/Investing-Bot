from investing_bot.order_spec_verifier import verify_order_spec, walk_limit_api_verified


def test_verify_order_spec_matches_when_normalized_values_align():
    intended = {
        "symbol": "SPY",
        "side": "BUY_TO_OPEN",
        "order_type": "LMT",
        "quantity": 2,
        "price": 1.25,
        "tif": "day",
    }
    actual = {
        "ticker": "SPY",
        "instruction": "buy",
        "type": "limit",
        "order_quantity": 2,
        "limit_price": 1.25,
        "time_in_force": "DAY",
    }
    verification = verify_order_spec(intended=intended, actual=actual)
    assert verification.matches
    assert verification.executable
    assert verification.diffs == ()


def test_verify_order_spec_flags_blocking_high_severity_mismatch():
    intended = {"symbol": "SPY", "side": "buy", "order_type": "limit", "quantity": 1}
    actual = {"symbol": "QQQ", "side": "buy", "order_type": "limit", "quantity": 1}

    verification = verify_order_spec(intended=intended, actual=actual)
    assert not verification.matches
    assert not verification.executable
    assert any(diff.field == "symbol" and diff.severity == "high" for diff in verification.diffs)


def test_walk_limit_capability_flag_reads_expected_key():
    assert not walk_limit_api_verified({})
    assert walk_limit_api_verified({"native_walk_limit_api_verified": True})
