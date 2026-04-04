from investing_bot.instrument_registry import InstrumentProfile, InstrumentRegistry


def test_instrument_registry_blocks_adjusted_and_nonstandard_by_default():
    registry = InstrumentRegistry()
    registry.register(
        InstrumentProfile(
            symbol="AAPL_20260410C200",
            underlying="AAPL",
            expiration_type="weekly",
            adjusted_option=True,
            defined_risk=True,
        )
    )

    allowed, reasons = registry.evaluate_trade(symbol="AAPL_20260410C200")
    assert not allowed
    assert "adjusted_option_blocked" in reasons
    assert "non_standard_expiration_blocked" in reasons


def test_instrument_registry_can_allow_nonstandard_when_enabled():
    registry = InstrumentRegistry.from_rows(
        [
            {
                "symbol": "SPY_20260417P400",
                "underlying": "SPY",
                "expiration_type": "quarterly",
                "adjusted_option": False,
                "defined_risk": True,
            }
        ]
    )
    allowed, reasons = registry.evaluate_trade(symbol="SPY_20260417P400", allow_non_standard=True)
    assert allowed
    assert reasons == ()
