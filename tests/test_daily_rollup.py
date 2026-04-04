from pathlib import Path

from investing_bot.daily_rollup import (
    build_daily_rollup,
    materialize_bucket_facts,
    materialize_policy_facts,
    materialize_trade_facts,
    persist_daily_rollup,
)


def _decision_rows():
    return [
        {
            "recorded_at": "2026-04-04T10:00:00Z",
            "data_source": "live",
            "bucket_key": "spy-0dte",
            "policy_version": "v1",
            "action": "passive_touch",
            "filled": True,
            "realized_alpha_density": 0.010,
            "slippage": 0.01,
            "modeled_slippage": 0.008,
            "prevailing_spread": 0.02,
            "fill_calibration_abs_error": 0.04,
            "target_notional": 1000,
            "realized_pnl": 12,
        },
        {
            "recorded_at": "2026-04-04T11:00:00Z",
            "data_source": "live",
            "bucket_key": "spy-0dte",
            "policy_version": "v1",
            "action": "cross_now",
            "filled": False,
            "realized_alpha_density": -0.002,
            "slippage": 0.03,
            "modeled_slippage": 0.01,
            "prevailing_spread": 0.04,
            "fill_calibration_abs_error": 0.10,
            "target_notional": 1200,
            "realized_pnl": -5,
        },
        {
            "recorded_at": "2026-04-05T10:00:00Z",
            "data_source": "paper",
            "bucket_key": "qqq-weekly",
            "policy_version": "v2",
            "action": "skip",
            "filled": True,
            "realized_alpha_density": 0.006,
            "slippage": 0.005,
            "modeled_slippage": 0.005,
            "prevailing_spread": 0.01,
            "fill_calibration_abs_error": 0.03,
            "target_notional": 800,
            "realized_pnl": 4,
        },
    ]


def test_materialize_trade_bucket_policy_facts():
    rows = _decision_rows()
    trade_facts = materialize_trade_facts(rows)
    bucket_facts = materialize_bucket_facts(rows)
    policy_facts = materialize_policy_facts(rows)

    assert len(trade_facts) == 2
    assert trade_facts[0].trade_count == 2
    assert trade_facts[0].source == "live"
    assert len(bucket_facts) == 2
    assert bucket_facts[0].bucket_key == "spy-0dte"
    assert len(policy_facts) == 2


def test_build_and_persist_daily_rollup(tmp_path: Path):
    decision_rows = _decision_rows()
    telemetry_rows = [
        {"recorded_at": "2026-04-04T10:00:00Z", "stream_gap_seconds": 1.0, "quote_age_ms": 500},
        {"recorded_at": "2026-04-04T11:00:00Z", "stream_gap_seconds": 6.0, "quote_age_ms": 1800},
    ]
    portfolio_rows = [
        {"recorded_at": "2026-04-04T10:00:00Z", "net_liquidation_value": 10000, "realized_pnl": 0, "total_max_loss": 200},
        {"recorded_at": "2026-04-04T12:00:00Z", "net_liquidation_value": 9800, "realized_pnl": -20, "total_max_loss": 250},
    ]

    rollup = build_daily_rollup(
        decision_rows=decision_rows,
        telemetry_rows=telemetry_rows,
        portfolio_rows=portfolio_rows,
    )
    assert rollup.telemetry_facts["2026-04-04"].stream_gap_p99_seconds == 6.0
    assert len(rollup.portfolio_facts) == 1
    assert rollup.portfolio_facts[0].max_drawdown_fraction > 0

    path = persist_daily_rollup(root_dir=tmp_path, rollup=rollup, as_of_date="2026-04-05")
    assert path.exists()
    assert "daily_rollup_2026-04-05.json" in path.name
