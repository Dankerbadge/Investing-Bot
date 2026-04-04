from investing_bot.ledger import PortfolioLedger
from investing_bot.portfolio_state import compute_portfolio_state


def test_compute_portfolio_state_tracks_realized_and_unrealized():
    ledger = PortfolioLedger.from_event_rows(
        [
            {
                "id": "1",
                "timestamp": "2026-04-04T10:00:00Z",
                "symbol": "SPY",
                "side": "buy",
                "quantity": 2,
                "price": 100.0,
                "commission": 1.0,
            },
            {
                "id": "2",
                "timestamp": "2026-04-04T10:10:00Z",
                "symbol": "SPY",
                "side": "sell",
                "quantity": 1,
                "price": 110.0,
                "commission": 1.0,
            },
        ]
    )
    state = compute_portfolio_state(
        ledger=ledger,
        market_quotes={"SPY": 120.0},
        starting_cash=1000.0,
        max_loss_by_symbol={"SPY": 25.0},
    )
    assert state.cash_balance == 908.0
    assert state.realized_pnl == 10.0
    assert state.unrealized_pnl == 20.0
    assert state.net_liquidation_value == 1028.0
    assert len(state.positions) == 1
    assert state.positions[0].max_loss == 25.0


def test_compute_portfolio_state_handles_short_position():
    ledger = PortfolioLedger.from_event_rows(
        [
            {
                "id": "1",
                "timestamp": "2026-04-04T10:00:00Z",
                "symbol": "QQQ",
                "side": "sell",
                "quantity": 1,
                "price": 100.0,
                "commission": 0.0,
            }
        ]
    )
    state = compute_portfolio_state(
        ledger=ledger,
        market_quotes={"QQQ": 90.0},
        starting_cash=1000.0,
    )
    assert state.realized_pnl == 0.0
    assert state.unrealized_pnl == 10.0
    assert state.positions[0].quantity == -1.0
