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

## Package Layout
- `src/investing_bot/scoring.py`: net executable edge formula.
- `src/investing_bot/gating.py`: quote freshness, spread, depth, fill-probability gates.
- `src/investing_bot/sizing.py`: Kelly and fractional Kelly controls.
- `src/investing_bot/risk.py`: concentration and gross-notional risk limits.
- `src/investing_bot/archive.py`: append-only JSONL history streams.
- `src/investing_bot/ghost_broker.py`: passive execution simulation.
- `src/investing_bot/execution_learning.py`: learns execution priors from your archive.
- `src/investing_bot/attribution.py`: per-trade counterfactual PnL decomposition.
- `src/investing_bot/pipeline.py`: end-to-end plan builder.

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
