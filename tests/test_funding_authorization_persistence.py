import pytest

from iceberg.capital.funding import FundingLedger, FundingStatus
from iceberg.exceptions import PermissionDeniedError
from iceberg.persistence.repositories import SQLiteStateStore
from iceberg.security.auth import Actor, ActorRole, AuthorizationContext, ai_context

from tests.conftest import D, TRADING_DATE, authenticated_reconciler_context, authenticated_user_context, ist_datetime


def test_fake_admin_string_cannot_confirm_funding():
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))

    with pytest.raises(TypeError):
        ledger.confirm(
            event.funding_id,
            confirmed_by="ADMIN",
            external_reference="fake",
            confirmed_at=ist_datetime(8, 1),
            effective_trading_date=TRADING_DATE,
        )


def test_funding_requires_permission():
    user_context = AuthorizationContext(Actor("user", ActorRole.USER, frozenset()))
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))

    with pytest.raises(PermissionDeniedError):
        ledger.confirm(
            event.funding_id,
            context=user_context,
            external_reference="no-permission",
            confirmed_at=ist_datetime(8, 1),
            effective_trading_date=TRADING_DATE,
        )


def test_pending_funding_survives_restart(tmp_path):
    store = SQLiteStateStore(tmp_path / "funding.sqlite3")
    ledger = FundingLedger(store=store)
    event = ledger.create_pending(D("25"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))

    restarted = FundingLedger(store=store)

    assert restarted.events()[0].funding_id == event.funding_id
    assert restarted.events()[0].status == FundingStatus.PENDING


def test_ai_context_cannot_confirm_funding():
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))

    with pytest.raises(PermissionDeniedError):
        ledger.confirm(
            event.funding_id,
            context=ai_context(),
            external_reference="ai",
            confirmed_at=ist_datetime(8, 1),
            effective_trading_date=TRADING_DATE,
        )


def test_ai_cannot_create_pending_funding():
    ledger = FundingLedger()

    with pytest.raises(PermissionDeniedError):
        ledger.create_pending(D("50"), context=ai_context(), requested_at=ist_datetime(8, 0))

    assert ledger.events() == ()


def test_created_by_comes_from_authenticated_actor():
    ledger = FundingLedger()

    event = ledger.create_pending(
        D("50"),
        context=authenticated_user_context("human-user-123"),
        requested_at=ist_datetime(8, 0),
    )

    assert event.created_by == "human-user-123"


def test_fake_user_string_cannot_create_funding():
    ledger = FundingLedger()

    with pytest.raises(TypeError):
        ledger.create_pending(D("50"), created_by="USER", requested_at=ist_datetime(8, 0))

    assert ledger.events() == ()


def test_funding_cannot_be_marked_applied_without_capital_manager_authority():
    ledger = FundingLedger()
    event = ledger.create_pending(D("50"), context=authenticated_user_context(), requested_at=ist_datetime(8, 0))
    ledger.confirm(
        event.funding_id,
        context=authenticated_reconciler_context(),
        external_reference="bank-ref-ai-apply",
        confirmed_at=ist_datetime(8, 1),
        effective_trading_date=TRADING_DATE,
    )

    with pytest.raises(PermissionDeniedError):
        ledger._mark_applied(event.funding_id, authority_token=object())

    assert ledger.events()[0].status == FundingStatus.CONFIRMED
