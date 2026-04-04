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
24. Broker-confirmed portfolio truth layer (`ledger.py` + `portfolio_state.py`) for realized/unrealized PnL, exposures, and max-loss snapshots.
25. Experiment lineage + deterministic replay (`experiment_registry.py` + `replay.py`) for policy/versioned decision auditing.
26. Operational telemetry + alerting + dashboard assembly (`telemetry.py` + `alerts.py` + `ops_dashboard.py`).
27. Corporate-action and instrument hygiene gates (`corp_actions.py` + `instrument_registry.py`) integrated into trade gating.
28. Champion/challenger governance and conservative online policy primitives (`champion_challenger.py` + `online_policy.py`).
29. Portfolio capital-efficiency scoring helpers and ruin guard controls (`capital_efficiency.py` + `ruin_guard.py`).
30. Recovery/bootstrap parity controls (`recovery.py`) to block entries until broker and local state reconcile.
31. Basket allocation + Greeks overlay (`allocator.py`) for portfolio-level capital deployment.
32. Off-policy evaluation (`off_policy_eval.py`) with IPS/DR estimators for safer challenger promotion.
33. Daily rollup and bucket-health materialization (`daily_rollup.py` + `bucket_health.py`) for durable evidence.
34. Chaos and fault-injection harness (`chaos_harness.py` + `fault_injection.py`) for restart/reconnect failure discipline.
35. Order-spec verification and execution audit (`order_spec_verifier.py` + `execution_audit.py`) for executable-style governance.
36. Alpha registry with pluggable alpha-family modules (`alpha_registry.py` + `alpha_families/`).
37. Campaign manager + sequential promotion/kill testing (`campaign_manager.py` + `sequential_tests.py`).
38. Point-in-time feature caching and tradable-universe construction (`feature_store.py` + `universe_builder.py`).

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
- `src/investing_bot/ledger.py`: broker-confirmed ledger entries and cash/position reconstruction.
- `src/investing_bot/portfolio_state.py`: canonical portfolio truth from ledger + quotes + Greeks.
- `src/investing_bot/experiment_registry.py`: policy/version/config/feature stamping for decision lineage.
- `src/investing_bot/replay.py`: deterministic replay over archived streams for offline validation.
- `src/investing_bot/telemetry.py`: telemetry aggregation for stream/budget/calibration drift metrics.
- `src/investing_bot/alerts.py`: threshold-driven operational alert generation.
- `src/investing_bot/ops_dashboard.py`: normalized operations dashboard payloads.
- `src/investing_bot/corp_actions.py`: adjusted/non-standard/assignment-risk context and hard-block helpers.
- `src/investing_bot/instrument_registry.py`: canonical instrument profiles and tradability checks.
- `src/investing_bot/champion_challenger.py`: replay/shadow/probe/live policy promotion decisions.
- `src/investing_bot/online_policy.py`: broker-confirmed online action learning primitives.
- `src/investing_bot/capital_efficiency.py`: alpha-density and capital-efficiency metrics.
- `src/investing_bot/ruin_guard.py`: drawdown/volatility/streak-based Kelly de-risking controls.
- `src/investing_bot/recovery.py`: restart/reconnect parity checks and broker-truth recovery gating.
- `src/investing_bot/allocator.py`: constrained basket optimizer and net-Greeks overlay helpers.
- `src/investing_bot/off_policy_eval.py`: propensity logging plus IPS/DR challenger evaluation.
- `src/investing_bot/daily_rollup.py`: durable daily trade/bucket/policy/portfolio materialization.
- `src/investing_bot/bucket_health.py`: bucket scoring and capital multiplier decisions from rollups + telemetry.
- `src/investing_bot/fault_injection.py`: deterministic stream/order fault injectors.
- `src/investing_bot/chaos_harness.py`: scenario runner for validating failure behavior.
- `src/investing_bot/order_spec_verifier.py`: intended-vs-broker order spec normalization and mismatch checks.
- `src/investing_bot/execution_audit.py`: lifecycle-level execution audits and summary metrics.
- `src/investing_bot/alpha_registry.py`: alpha family specs, signal registration, and candidate conversion.
- `src/investing_bot/alpha_families/`: built-in alpha families (`filing_vol`, `post_event_iv`, `open_drive`).
- `src/investing_bot/campaign_manager.py`: probe-budget allocation and stage decisions for alpha campaigns.
- `src/investing_bot/sequential_tests.py`: lower/upper confidence-bound utilities for promote/kill logic.
- `src/investing_bot/feature_store.py`: point-in-time feature snapshots and merged feature payload helpers.
- `src/investing_bot/universe_builder.py`: liquidity/instrument-aware universe filtering and family-ready row mapping.

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
