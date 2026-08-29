from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from iceberg.domain.enums import FundingStatus, Permission
from iceberg.domain.models import money, require_aware
from iceberg.exceptions import FundingError, PermissionDeniedError
from iceberg.security.auth import AuthorizationContext


_FUNDING_LEDGER_TOKEN = object()


@dataclass
class FundingEvent:
    funding_id: str
    amount: Decimal
    currency: str
    requested_at: datetime
    confirmed_at: datetime | None = None
    effective_trading_date: date | None = None
    external_reference: str | None = None
    status: FundingStatus = FundingStatus.PENDING
    created_by: str = "USER"
    notes: str = ""

    def __post_init__(self) -> None:
        require_aware(self.requested_at, "requested_at")
        if self.confirmed_at is not None:
            require_aware(self.confirmed_at, "confirmed_at")
        self.amount = money(self.amount)
        if self.amount <= 0:
            raise FundingError("funding amount must be positive")
        self.currency = self.currency.upper()


class FundingLedger:
    """Append-only-ish funding ledger for externally confirmed user capital."""

    def __init__(self, store=None) -> None:
        self.store = store
        self._events: dict[str, FundingEvent] = {}
        if store is not None:
            self._events = {event.funding_id: event for event in store.load_funding_events()}

    def create_pending(
        self,
        amount: Decimal,
        *,
        currency: str = "INR",
        context: AuthorizationContext,
        requested_at: datetime,
        notes: str = "",
    ) -> FundingEvent:
        context.require(Permission.FUNDING_REQUEST)
        event = FundingEvent(
            funding_id=str(uuid4()),
            amount=amount,
            currency=currency,
            created_by=context.actor.actor_id,
            requested_at=requested_at,
            notes=notes,
        )
        self._events[event.funding_id] = event
        self._persist(event)
        return event

    def confirm(
        self,
        funding_id: str,
        *,
        context: AuthorizationContext,
        external_reference: str,
        confirmed_at: datetime,
        effective_trading_date: date,
    ) -> FundingEvent:
        context.require(Permission.FUNDING_CONFIRM)
        require_aware(confirmed_at, "confirmed_at")
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.PENDING:
            raise FundingError("only pending funding can be confirmed")
        event.status = FundingStatus.CONFIRMED
        event.confirmed_at = confirmed_at
        event.external_reference = external_reference
        event.effective_trading_date = effective_trading_date
        self._persist(event)
        return event

    def reject(self, funding_id: str, *, context: AuthorizationContext, notes: str = "") -> FundingEvent:
        context.require(Permission.CAPITAL_ADMIN)
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.PENDING:
            raise FundingError("only pending funding can be rejected")
        event.status = FundingStatus.REJECTED
        event.notes = notes or event.notes
        self._persist(event)
        return event

    def cancel(self, funding_id: str, *, context: AuthorizationContext, notes: str = "") -> FundingEvent:
        context.require(Permission.CAPITAL_ADMIN)
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.PENDING:
            raise FundingError("only pending funding can be cancelled")
        event.status = FundingStatus.CANCELLED
        event.notes = notes or event.notes
        self._persist(event)
        return event

    def _mark_applied(self, funding_id: str, *, authority_token: object) -> FundingEvent:
        if authority_token is not _FUNDING_LEDGER_TOKEN:
            raise PermissionDeniedError("funding can only be applied by the capital manager")
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.CONFIRMED:
            raise FundingError("only confirmed funding can be applied")
        event.status = FundingStatus.APPLIED
        self._persist(event)
        return event

    def confirmed_unapplied(self) -> list[FundingEvent]:
        return [event for event in self._events.values() if event.status is FundingStatus.CONFIRMED]

    def events(self) -> tuple[FundingEvent, ...]:
        return tuple(self._events.values())

    def _require_event(self, funding_id: str) -> FundingEvent:
        try:
            return self._events[funding_id]
        except KeyError as exc:
            raise FundingError(f"unknown funding event {funding_id}") from exc

    def _persist(self, event: FundingEvent) -> None:
        if self.store is not None:
            self.store.save_funding_event(event)
