from investing_bot.capabilities import CapabilityRegistry, action_is_allowed


def test_native_walk_limit_requires_verified_capability():
    registry = CapabilityRegistry()
    assert (
        action_is_allowed(
            action="native_walk_limit",
            registry=registry,
            is_realtime_quote=True,
            is_stock_etf_option=True,
            in_regular_hours=True,
        )
        is False
    )

    registry.set_verified("native_walk_limit_api", True)
    assert (
        action_is_allowed(
            action="native_walk_limit",
            registry=registry,
            is_realtime_quote=True,
            is_stock_etf_option=True,
            in_regular_hours=True,
        )
        is True
    )


def test_non_native_actions_are_allowed():
    assert action_is_allowed(action="passive_touch", registry=None) is True
