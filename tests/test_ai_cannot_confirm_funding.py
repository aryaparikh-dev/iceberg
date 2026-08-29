import pytest

from iceberg.capital.funding import FundingLedger
from iceberg.exceptions import PermissionDeniedError
from iceberg.security.auth import ai_context

from tests.conftest import D, TRADING_DATE, authenticated_user_context, ist_datetime


def test_ai_cannot_mark_funding_confirmed():
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))

    with pytest.raises(PermissionDeniedError):
        ledger.confirm(
            event.funding_id,
            context=ai_context(),
            external_reference="not-allowed",
            confirmed_at=ist_datetime(8, 1),
            effective_trading_date=TRADING_DATE,
        )
