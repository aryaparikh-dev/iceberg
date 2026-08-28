from iceberg.capital.funding import FundingLedger
from iceberg.capital.manager import CapitalManager
from iceberg.security.auth import external_reconciler_context

from tests.conftest import D, TRADING_DATE, ist_datetime


def test_intraday_topup_forbidden_in_v1_even_after_confirmation(safe_context):
    assert safe_context.settings.capital.intraday_capital_topups_allowed is False
    ledger = FundingLedger()
    manager = CapitalManager(safe_context.guard, ledger, safe_context.settings, safe_context.calendar)
    manager.start_trading_day(TRADING_DATE, ist_datetime(9, 0))
    event = ledger.create_pending(D("999"), created_by="USER", requested_at=ist_datetime(11, 0))
    ledger.confirm(
        event.funding_id,
        context=external_reconciler_context(),
        external_reference="bank-ref-3",
        confirmed_at=ist_datetime(11, 5),
        effective_trading_date=TRADING_DATE,
    )

    manager.apply_intraday_confirmations(TRADING_DATE, ist_datetime(11, 10))

    assert safe_context.guard.state.daily_starting_capital == D("100")
    assert safe_context.guard.state.available_cash == D("100")
