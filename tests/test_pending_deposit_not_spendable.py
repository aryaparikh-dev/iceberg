from iceberg.capital.funding import FundingLedger
from iceberg.capital.manager import CapitalManager

from tests.conftest import D, TRADING_DATE, authenticated_user_context, ist_datetime


def test_pending_deposit_is_never_spendable(safe_context):
    ledger = FundingLedger()
    ledger.create_pending(D("1000"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))
    manager = CapitalManager(safe_context.guard, ledger, safe_context.settings, safe_context.calendar)

    manager.start_trading_day(TRADING_DATE, ist_datetime(9, 0))

    assert safe_context.guard.state.daily_starting_capital == D("100")
    assert safe_context.guard.state.available_cash == D("100")
