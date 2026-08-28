from iceberg.capital.funding import FundingLedger
from iceberg.capital.manager import CapitalManager
from iceberg.security.auth import external_reconciler_context

from tests.conftest import D, TRADING_DATE, ist_datetime


def test_confirmed_intraday_deposit_becomes_eligible_next_trading_day_by_default(safe_context):
    ledger = FundingLedger()
    manager = CapitalManager(safe_context.guard, ledger, safe_context.settings, safe_context.calendar)
    manager.start_trading_day(TRADING_DATE, ist_datetime(9, 0))

    event = ledger.create_pending(D("50"), created_by="USER", requested_at=ist_datetime(10, 0))
    ledger.confirm(
        event.funding_id,
        context=external_reconciler_context(),
        external_reference="bank-ref-2",
        confirmed_at=ist_datetime(10, 1),
        effective_trading_date=TRADING_DATE,
    )

    assert safe_context.guard.state.daily_starting_capital == D("100")

    manager.start_trading_day(ist_datetime(9, 0, day=6).date(), ist_datetime(9, 0, day=6))

    assert safe_context.guard.state.daily_starting_capital == D("150")
