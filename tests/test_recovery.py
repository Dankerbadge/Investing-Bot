from investing_bot.ledger import LedgerEntry, PortfolioLedger
from investing_bot.recovery import (
    detect_orphaned_orders,
    recover_account_state,
    require_broker_parity_before_entries,
)


def _ledger_with_buy() -> PortfolioLedger:
    ledger = PortfolioLedger()
    ledger.add_entry(
        LedgerEntry(
            entry_id="0",
            timestamp="2026-04-04T09:30:00Z",
            symbol="CASH",
            side="cash",
            cash_delta=1000.0,
            broker_confirmed=True,
        )
    )
    ledger.add_entry(
        LedgerEntry(
            entry_id="1",
            timestamp="2026-04-04T10:00:00Z",
            symbol="SPY",
            side="buy",
            quantity=1,
            price=100.0,
            fee=0.0,
            broker_confirmed=True,
        )
    )
    return ledger


def test_detect_orphaned_orders_diffs_broker_and_local():
    orphaned, stale = detect_orphaned_orders(
        broker_open_orders=[{"order_id": "b1"}, {"order_id": "b2"}],
        local_open_orders=[{"order_id": "b2"}, {"order_id": "l1"}],
    )
    assert orphaned == ("b1",)
    assert stale == ("l1",)


def test_recovery_passes_when_positions_and_orders_match():
    state = recover_account_state(
        ledger=_ledger_with_buy(),
        balances={"cash_balance": 900.0},
        positions=[{"symbol": "SPY", "quantity": 1}],
        open_orders=[],
        local_open_orders=[],
    )
    allow, reasons = require_broker_parity_before_entries(state)
    assert allow
    assert reasons == ()
    assert state.parity_ok


def test_recovery_blocks_on_position_mismatch_and_orphaned_orders():
    state = recover_account_state(
        ledger=_ledger_with_buy(),
        balances={"cash_balance": 900.0},
        positions=[{"symbol": "SPY", "quantity": 0}],
        open_orders=[{"order_id": "b-1"}],
        local_open_orders=[],
    )
    allow, reasons = require_broker_parity_before_entries(state)
    assert not allow
    assert "position_mismatch" in reasons
    assert "orphaned_broker_orders" in reasons
