# Investing-Bot

Execution-aware trading architecture upgrade based on the audit recommendation to optimize **net executable edge**, not raw model residuals.

## What Changed
This repo now includes a working Python starter focused on the highest-ROI path:

1. Dynamic net-edge scoring (replace static threshold logic).
2. Liquidity/execution gating before trade selection.
3. Fractional Kelly sizing with hard caps.
4. Concentration-first portfolio construction (top 1-3 setups, low correlation).
5. First-party archive streams for chain snapshots, signals, orders, and fills.
6. Ghost broker simulation for passive fill and cancel/replace behavior.
7. Closed-loop execution learning: archive-derived fill/slippage/decay priors feed score and size.
8. Counterfactual attribution to isolate selection vs execution vs sizing leakage.
9. Source-segregated execution learning (`live` / `paper` / `ghost`) with hierarchical bucket shrinkage.
10. Alpha-density ranking and execution-style optimization with request-budget penalties.
11. Contract-hygiene kill switches for adjusted/nonstandard/locked-or-crossed options.
12. Broker-truth reconciliation for order lifecycle and delayed-quote detection.
13. Calibration metrics (Brier score, pinball loss, reliability bins) for execution-learning quality.
14. Native walk-limit vs synthetic-ladder execution paths with separate churn/race penalties.
15. Quality-stamped archive rows and quality-weighted execution priors.
16. Broker-confirmed-only policy learning and explicit policy skip action.
17. Exit policy engine scaffold (assignment/drift/quote-quality aware).
18. Drift governor to auto-reduce Kelly during calibration stress.
19. Native walk-limit is only selectable when API executability is explicitly verified.
20. Stream subscription manager to avoid duplicate churn and maintain deterministic stream reconciliation.
21. Latency profile and kill-switch path to block stale/slow decisions before capital is deployed.
22. Promotion/deployment control layer for `disabled -> shadow -> probe -> scaled_1 -> scaled_2 -> scaled_3 -> mature` action buckets.
23. Event/regime context integration (`SEC` filing windows + `FRED/Cboe` regime tags) feeding policy, promotion, and deployment controls.

## Package Layout
- `src/investing_bot/scoring.py`: net executable edge formula.
- `src/investing_bot/gating.py`: quote freshness, spread, depth, fill-probability gates.
- `src/investing_bot/sizing.py`: Kelly and fractional Kelly controls.
- `src/investing_bot/risk.py`: concentration and gross-notional risk limits.
- `src/investing_bot/archive.py`: append-only JSONL history streams.
- `src/investing_bot/ghost_broker.py`: passive execution simulation.
- `src/investing_bot/execution_learning.py`: learns execution priors from your archive.
- `src/investing_bot/execution_style.py`: chooses entry style and applies request/race penalties.
- `src/investing_bot/attribution.py`: per-trade counterfactual PnL decomposition.
- `src/investing_bot/reconciliation.py`: reconciles order lifecycle from broker/account events.
- `src/investing_bot/calibration.py`: fill/slippage calibration metrics and reliability summaries.
- `src/investing_bot/policy.py`: broker-confirmed policy updates and entry action selection.
- `src/investing_bot/exit_policy.py`: exit/hedge decision policy scaffold.
- `src/investing_bot/pipeline.py`: end-to-end plan builder.
- `src/investing_bot/ghost_broker.py`: style-aware fill simulation (passive, native walk, synthetic ladder, cross).
- `src/investing_bot/stream_manager.py`: serialized stream subscription reconciliation.
- `src/investing_bot/latency.py`: latency decomposition and latency kill switches.
- `src/investing_bot/promotion.py`: promotion/demotion rules for live deployment stages.
- `src/investing_bot/deployment_control.py`: capital multiplier and pause decisions from stage + drift + broker risk.
- `src/investing_bot/capabilities.py`: broker/API capability registry and action gating.
- `src/investing_bot/event_context.py`: filing/earnings/macro/ex-dividend event risk tagging.
- `src/investing_bot/regime.py`: volatility/liquidity/macro/crowding regime tagging.

## Core Score
```python
net_edge = (
    surface_residual * convergence_probability * fill_probability
    - spread_cost
    - hedge_cost
    - stale_quote_penalty
    - event_gap_penalty
    - capital_lockup_penalty
    - slippage_p95_penalty
    - post_fill_alpha_decay_penalty
    - uncertainty_penalty
    - execution_penalty
)
```

## Archive Layout
Archive streams are now source-separated:
- `orders/live/*.jsonl`
- `orders/paper/*.jsonl`
- `orders/ghost/*.jsonl`
- same structure for `fills`, `signals`, and `chain_snapshots`.

## Config + Example Data
- `config/trading_profile.json`
- `examples/sample_candidates.json`

## Run Tests
```bash
cd /Users/dankerbadge/Documents/Investing\ Bot/Investing-Bot
python3 -m pytest
```

## Legacy Document Deliverable
- `Deep Research Report - Profit Maximization - Tracked Changes (Claude).docx`
