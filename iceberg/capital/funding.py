from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from iceberg.domain.enums import FundingStatus
from iceberg.domain.models import money, require_aware
from iceberg.exceptions import FundingError, PermissionDeniedError


AUTHORIZED_CONFIRMERS = {"USER", "EXTERNAL_RECONCILER", "ADMIN"}


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

    def __init__(self) -> None:
        self._events: dict[str, FundingEvent] = {}

    def create_pending(
        self,
        amount: Decimal,
        *,
        currency: str = "INR",
        created_by: str,
        requested_at: datetime,
        notes: str = "",
    ) -> FundingEvent:
        event = FundingEvent(
            funding_id=str(uuid4()),
            amount=amount,
            currency=currency,
            created_by=created_by,
            requested_at=requested_at,
            notes=notes,
        )
        self._events[event.funding_id] = event
        return event

    def confirm(
        self,
        funding_id: str,
        *,
        confirmed_by: str,
        external_reference: str,
        confirmed_at: datetime,
        effective_trading_date: date,
    ) -> FundingEvent:
        actor = confirmed_by.upper()
        if actor == "AI" or actor not in AUTHORIZED_CONFIRMERS:
            raise PermissionDeniedError("AI or unauthorized actors cannot confirm funding")
        require_aware(confirmed_at, "confirmed_at")
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.PENDING:
            raise FundingError("only pending funding can be confirmed")
        event.status = FundingStatus.CONFIRMED
        event.confirmed_at = confirmed_at
        event.external_reference = external_reference
        event.effective_trading_date = effective_trading_date
        return event

    def reject(self, funding_id: str, *, actor: str, notes: str = "") -> FundingEvent:
        if actor.upper() == "AI":
            raise PermissionDeniedError("AI cannot reject funding")
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.PENDING:
            raise FundingError("only pending funding can be rejected")
        event.status = FundingStatus.REJECTED
        event.notes = notes or event.notes
        return event

    def cancel(self, funding_id: str, *, actor: str, notes: str = "") -> FundingEvent:
        if actor.upper() == "AI":
            raise PermissionDeniedError("AI cannot cancel funding")
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.PENDING:
            raise FundingError("only pending funding can be cancelled")
        event.status = FundingStatus.CANCELLED
        event.notes = notes or event.notes
        return event

    def mark_applied(self, funding_id: str) -> FundingEvent:
        event = self._require_event(funding_id)
        if event.status is not FundingStatus.CONFIRMED:
            raise FundingError("only confirmed funding can be applied")
        event.status = FundingStatus.APPLIED
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
