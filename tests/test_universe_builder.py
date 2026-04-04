from investing_bot.alpha_registry import build_default_alpha_registry
from investing_bot.instrument_registry import InstrumentProfile, InstrumentRegistry
from investing_bot.universe_builder import (
    UniverseConstraints,
    build_alpha_universe,
    build_tradable_universe,
    rows_for_alpha_family,
)


def _rows():
    return [
        {
            "symbol": "SPY",
            "underlying": "SPY",
            "liquidity_score": 0.9,
            "book_depth_contracts": 150,
            "spread_cost": 0.01,
            "quote_age_seconds": 0.5,
            "sec_recent_filing": True,
            "filing_shock_score": 0.4,
            "iv_minus_realized": 0.05,
            "hours_since_event": 2,
            "post_event_iv_ratio": 1.1,
            "mean_reversion_score": 0.4,
            "minutes_from_open": 5,
            "opening_drive_score": 0.6,
            "quote_quality_tier": "realtime",
        },
        {
            "symbol": "IWM",
            "underlying": "IWM",
            "liquidity_score": 0.2,
            "book_depth_contracts": 10,
            "spread_cost": 0.2,
            "quote_age_seconds": 8.0,
            "quote_quality_tier": "delayed",
        },
    ]


def test_build_tradable_universe_filters_low_quality_rows():
    registry = InstrumentRegistry()
    registry.register(InstrumentProfile(symbol="SPY", underlying="SPY", expiration_type="standard", adjusted_option=False, defined_risk=True))
    registry.register(InstrumentProfile(symbol="IWM", underlying="IWM", expiration_type="standard", adjusted_option=False, defined_risk=True))

    members = build_tradable_universe(
        _rows(),
        constraints=UniverseConstraints(require_realtime_quotes=True),
        instrument_registry=registry,
    )

    assert len(members) == 1
    assert members[0].symbol == "SPY"
    assert members[0].eligible


def test_rows_for_alpha_family_requires_feature_presence():
    alpha_registry = build_default_alpha_registry()
    rows = _rows()

    filing_rows = rows_for_alpha_family(rows, family_name="filing_vol", alpha_registry=alpha_registry)
    assert len(filing_rows) == 1
    assert filing_rows[0]["symbol"] == "SPY"


def test_build_alpha_universe_maps_rows_per_family():
    alpha_registry = build_default_alpha_registry()
    registry = InstrumentRegistry()
    registry.register(InstrumentProfile(symbol="SPY", underlying="SPY", expiration_type="standard", adjusted_option=False, defined_risk=True))

    universe = build_alpha_universe(
        _rows(),
        alpha_registry=alpha_registry,
        constraints=UniverseConstraints(require_realtime_quotes=True),
        instrument_registry=registry,
    )

    assert "filing_vol" in universe
    assert "post_event_iv" in universe
    assert "open_drive" in universe
    assert all(len(rows) == 1 for rows in universe.values())
