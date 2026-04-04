from __future__ import annotations

import json

from investing_bot.execution_learning import adjustments_for_candidate, learn_execution_priors
from investing_bot.models import Candidate


def _append_jsonl(path, payloads):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(json.dumps(payload))
            handle.write("\n")


def test_learn_execution_priors_and_adjustments(tmp_path):
    archive_root = tmp_path / "archive"

    _append_jsonl(
        archive_root / "orders" / "2026-04-04.jsonl",
        [
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 10},
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 10},
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 10},
        ],
    )
    _append_jsonl(
        archive_root / "fills" / "2026-04-04.jsonl",
        [
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "fill_quantity": 20,
                "slippage_dollars": 0.01,
                "post_fill_alpha_decay": 0.005,
            },
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "fill_quantity": 7,
                "slippage_dollars": 0.03,
                "post_fill_alpha_decay": 0.012,
            },
        ],
    )
    _append_jsonl(
        archive_root / "signals" / "2026-04-04.jsonl",
        [
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "predicted_net_edge": 0.04,
                "realized_net_edge": 0.03,
            }
        ],
    )

    priors = learn_execution_priors(archive_root)
    assert any("iv_repricing" in key for key in priors)

    candidate = Candidate(
        ticker="SPY-TEST",
        underlying="SPY",
        event_key="event-1",
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=0.05,
        convergence_probability=0.65,
        fill_probability=0.7,
        spread_cost=0.01,
        hedge_cost=0.004,
        stale_quote_penalty=0.002,
        event_gap_penalty=0.003,
        capital_lockup_penalty=0.002,
        confidence=0.7,
        book_depth_contracts=100,
        quote_age_seconds=1.0,
        payoff_multiple=1.2,
        loss_multiple=1.0,
    )
    adj = adjustments_for_candidate(candidate, priors)

    assert adj.expected_fill_probability is not None
    assert 0.0 <= adj.expected_fill_probability <= 1.0
    assert adj.slippage_p95_penalty >= 0.0
    assert adj.post_fill_alpha_decay_penalty >= 0.0


def test_execution_learning_respects_allowed_sources(tmp_path):
    archive_root = tmp_path / "archive"

    _append_jsonl(
        archive_root / "orders" / "live" / "2026-04-04.jsonl",
        [
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 10, "data_source": "live"},
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 10, "data_source": "live"},
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 10, "data_source": "live"},
        ],
    )
    _append_jsonl(
        archive_root / "fills" / "live" / "2026-04-04.jsonl",
        [
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "fill_quantity": 28,
                "slippage_dollars": 0.01,
                "post_fill_alpha_decay": 0.004,
                "data_source": "live",
            }
        ],
    )

    _append_jsonl(
        archive_root / "orders" / "paper" / "2026-04-04.jsonl",
        [
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 20, "data_source": "paper"},
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 20, "data_source": "paper"},
            {"strategy_family": "iv_repricing", "underlying": "SPY", "order_quantity": 20, "data_source": "paper"},
        ],
    )
    _append_jsonl(
        archive_root / "fills" / "paper" / "2026-04-04.jsonl",
        [
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "fill_quantity": 4,
                "slippage_dollars": 0.05,
                "post_fill_alpha_decay": 0.03,
                "data_source": "paper",
            }
        ],
    )

    live_priors = learn_execution_priors(archive_root, allowed_sources=("live",))
    mixed_priors = learn_execution_priors(archive_root, allowed_sources=("live", "paper"))

    candidate = Candidate(
        ticker="SPY-TEST",
        underlying="SPY",
        event_key="event-1",
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=0.05,
        convergence_probability=0.65,
        fill_probability=0.7,
        spread_cost=0.01,
        hedge_cost=0.004,
        stale_quote_penalty=0.002,
        event_gap_penalty=0.003,
        capital_lockup_penalty=0.002,
        confidence=0.7,
        book_depth_contracts=100,
        quote_age_seconds=1.0,
        payoff_multiple=1.2,
        loss_multiple=1.0,
    )
    live_adj = adjustments_for_candidate(candidate, live_priors)
    mixed_adj = adjustments_for_candidate(candidate, mixed_priors)

    assert (live_adj.expected_fill_probability or 0.0) > (mixed_adj.expected_fill_probability or 0.0)


def test_execution_learning_downweights_delayed_low_reliability_samples(tmp_path):
    archive_root = tmp_path / "archive"
    _append_jsonl(
        archive_root / "orders" / "live" / "2026-04-04.jsonl",
        [
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "order_quantity": 10,
                "data_source": "live",
                "quote_quality_tier": "realtime",
                "book_reliability_score": 0.95,
            },
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "order_quantity": 10,
                "data_source": "live",
                "quote_quality_tier": "realtime",
                "book_reliability_score": 0.95,
            },
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "order_quantity": 10,
                "data_source": "live",
                "quote_quality_tier": "delayed",
                "book_reliability_score": 0.50,
            },
        ],
    )
    _append_jsonl(
        archive_root / "fills" / "live" / "2026-04-04.jsonl",
        [
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "fill_quantity": 10,
                "data_source": "live",
                "quote_quality_tier": "realtime",
                "book_reliability_score": 0.95,
            },
            {
                "strategy_family": "iv_repricing",
                "underlying": "SPY",
                "fill_quantity": 10,
                "data_source": "live",
                "quote_quality_tier": "realtime",
                "book_reliability_score": 0.95,
            },
        ],
    )

    priors = learn_execution_priors(archive_root, allowed_sources=("live",))
    candidate = Candidate(
        ticker="SPY-TEST",
        underlying="SPY",
        event_key="event-1",
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=0.05,
        convergence_probability=0.65,
        fill_probability=0.7,
        spread_cost=0.01,
        hedge_cost=0.004,
        stale_quote_penalty=0.002,
        event_gap_penalty=0.003,
        capital_lockup_penalty=0.002,
        confidence=0.7,
        book_depth_contracts=100,
        quote_age_seconds=1.0,
        payoff_multiple=1.2,
        loss_multiple=1.0,
    )
    adj = adjustments_for_candidate(candidate, priors)
    assert (adj.expected_fill_probability or 0.0) > 0.75
