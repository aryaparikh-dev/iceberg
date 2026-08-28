import pytest

from iceberg.capital.funding import FundingLedger
from iceberg.capital.manager import CapitalManager
from iceberg.security.auth import external_reconciler_context

from tests.conftest import D, TRADING_DATE, ist_datetime


def test_capital_snapshot_cannot_be_arbitrarily_increased(safe_context):
    with pytest.raises(TypeError):
        safe_context.guard.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 1), capital_amount=D("999999"))


def test_locked_daily_snapshot_cannot_be_altered_or_reset_loss_counter(safe_context):
    safe_context.guard.state.consecutive_losses = 2
    safe_context.guard.state.next_day_capital = D("999999")

    created = safe_context.guard.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 1))

    assert created is False
    assert safe_context.guard.state.daily_starting_capital == D("100")
    assert safe_context.guard.state.consecutive_losses == 2


def test_confirmed_funding_applied_only_once(safe_context):
    from iceberg.capital.guard import CapitalGuard
    from iceberg.market.calendar import TradingCalendar

    guard = CapitalGuard.initial(D("100"), settings=safe_context.settings)
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), created_by="USER", requested_at=ist_datetime(8, 0))
    ledger.confirm(
        event.funding_id,
        context=external_reconciler_context(),
        external_reference="bank-ref-once",
        confirmed_at=ist_datetime(8, 1),
        effective_trading_date=TRADING_DATE,
    )
    manager = CapitalManager(
        guard,
        ledger,
        safe_context.settings,
        TradingCalendar(provider_verified=True),
    )

    manager.start_trading_day(TRADING_DATE, ist_datetime(9, 0))
    manager.start_trading_day(TRADING_DATE, ist_datetime(9, 5))

    assert guard.state.daily_starting_capital == D("150")
    assert ledger.events()[0].status.value == "APPLIED"
