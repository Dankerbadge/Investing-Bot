from investing_bot.ledger import LedgerEntry, PortfolioLedger


def test_portfolio_ledger_positions_and_cash():
    ledger = PortfolioLedger()
    ledger.add_entry(
        LedgerEntry(
            entry_id="1",
            timestamp="2026-04-04T10:00:00Z",
            symbol="SPY",
            side="buy",
            quantity=2,
            price=100.0,
            fee=1.0,
            broker_confirmed=True,
        )
    )
    ledger.add_entry(
        LedgerEntry(
            entry_id="2",
            timestamp="2026-04-04T10:05:00Z",
            symbol="SPY",
            side="sell",
            quantity=1,
            price=110.0,
            fee=1.0,
            broker_confirmed=True,
        )
    )
    assert ledger.positions() == {"SPY": 1.0}
    assert ledger.cash_balance(starting_cash=1000.0) == 908.0


def test_portfolio_ledger_ignores_unconfirmed_entries_by_default():
    ledger = PortfolioLedger.from_event_rows(
        [
            {
                "id": "1",
                "timestamp": "2026-04-04T10:00:00Z",
                "symbol": "QQQ",
                "side": "buy",
                "quantity": 1,
                "price": 100.0,
                "broker_confirmed": False,
            }
        ]
    )
    assert ledger.positions() == {}
    assert ledger.positions(broker_confirmed_only=False) == {"QQQ": 1.0}
