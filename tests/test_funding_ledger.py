from iceberg.capital.funding import FundingLedger, FundingStatus
from iceberg.security.auth import external_reconciler_context

from tests.conftest import D, ist_datetime


def test_funding_ledger_records_pending_and_confirmed_external_events():
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), created_by="USER", requested_at=ist_datetime(8, 0))

    assert event.status == FundingStatus.PENDING

    confirmed = ledger.confirm(
        event.funding_id,
        context=external_reconciler_context(),
        external_reference="bank-ref-1",
        confirmed_at=ist_datetime(8, 10),
        effective_trading_date=ist_datetime(8, 10).date(),
    )

    assert confirmed.status == FundingStatus.CONFIRMED
    assert confirmed.external_reference == "bank-ref-1"
