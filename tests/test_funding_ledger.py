from iceberg.capital.funding import FundingLedger, FundingStatus

from tests.conftest import D, authenticated_reconciler_context, authenticated_user_context, ist_datetime


def test_funding_ledger_records_pending_and_confirmed_external_events():
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))

    assert event.status == FundingStatus.PENDING

    confirmed = ledger.confirm(
        event.funding_id,
        context=authenticated_reconciler_context(),
        external_reference="bank-ref-1",
        confirmed_at=ist_datetime(8, 10),
        effective_trading_date=ist_datetime(8, 10).date(),
    )

    assert confirmed.status == FundingStatus.CONFIRMED
    assert confirmed.external_reference == "bank-ref-1"
