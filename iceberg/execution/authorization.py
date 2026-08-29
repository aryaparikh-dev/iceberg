from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from iceberg.domain.enums import TradeSide
from iceberg.domain.models import TradeProposal, money, require_aware
from iceberg.exceptions import AuthorizationError


_AUTHORIZATION_ISSUER_TOKEN = object()


@dataclass
class ExecutionAuthorization:
    """Trusted authorization produced by the risk/execution path.

    This is an architectural hardening boundary, not a Python security sandbox.
    Python code running in the same interpreter can still inspect private module
    internals, so future live trading must rely on process isolation and broker-
    side authorization as well. V1 uses this object to ensure normal strategy
    code cannot submit an arbitrary public boolean approval.
    """

    decision_id: str
    symbol: str
    side: TradeSide
    quantity: int
    approved_price: Decimal
    estimated_costs: Decimal
    capital_required: Decimal
    approved_at: datetime
    valid_until: datetime
    trading_date: date
    charge_schedule_version: str
    authorization_id: str = field(default_factory=lambda: f"AUTH-{uuid4()}")
    _issuer_token: object = field(default=None, repr=False, compare=False)
    _used: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer_token is not _AUTHORIZATION_ISSUER_TOKEN:
            raise AuthorizationError("execution authorization must be issued by the trusted risk path")
        require_aware(self.approved_at, "approved_at")
        require_aware(self.valid_until, "valid_until")
        if self.valid_until < self.approved_at:
            raise AuthorizationError("authorization expiry precedes approval")
        self.symbol = self.symbol.upper()
        self.approved_price = money(self.approved_price)
        self.estimated_costs = money(self.estimated_costs)
        self.capital_required = money(self.capital_required)
        if self.quantity <= 0:
            raise AuthorizationError("authorization quantity must be positive")

    def consume_for(self, proposal: TradeProposal, now: datetime) -> None:
        if self._used:
            raise AuthorizationError("execution authorization is single-use")
        self._require_proposal_match(proposal)
        self.validate_session(now)
        self._used = True

    def matches(self, proposal: TradeProposal) -> bool:
        try:
            if self._used:
                return False
            self._require_proposal_match(proposal)
        except AuthorizationError:
            return False
        return True

    def validate_session(self, now: datetime) -> None:
        require_aware(now, "now")
        if now.date() != self.trading_date:
            raise AuthorizationError("AUTHORIZATION_SESSION_MISMATCH")
        if now > self.valid_until:
            raise AuthorizationError("AUTHORIZATION_EXPIRED")

    def _require_proposal_match(self, proposal: TradeProposal) -> None:
        if proposal.decision_id != self.decision_id:
            raise AuthorizationError("authorization decision mismatch")
        if proposal.symbol != self.symbol:
            raise AuthorizationError("authorization symbol mismatch")
        if proposal.side is not self.side:
            raise AuthorizationError("authorization side mismatch")
        if proposal.quantity is not None and proposal.quantity != self.quantity:
            raise AuthorizationError("authorization quantity mismatch")
        if proposal.proposed_price != self.approved_price:
            raise AuthorizationError("authorization price mismatch")


def _issue_execution_authorization(
    *,
    decision_id: str,
    symbol: str,
    side: TradeSide,
    quantity: int,
    approved_price: Decimal,
    estimated_costs: Decimal,
    capital_required: Decimal,
    approved_at: datetime,
    valid_until: datetime,
    trading_date: date,
    charge_schedule_version: str,
) -> ExecutionAuthorization:
    return ExecutionAuthorization(
        decision_id=decision_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        approved_price=approved_price,
        estimated_costs=estimated_costs,
        capital_required=capital_required,
        approved_at=approved_at,
        valid_until=valid_until,
        trading_date=trading_date,
        charge_schedule_version=charge_schedule_version,
        _issuer_token=_AUTHORIZATION_ISSUER_TOKEN,
    )
