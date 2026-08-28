from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from iceberg.domain.enums import ApprovalStatus, AssetClass, MarketRegime, OrderStatus, SignalType, TradeSide
from iceberg.exceptions import FailClosedError


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value))


def require_aware(timestamp: datetime, field_name: str = "timestamp") -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise FailClosedError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        require_aware(self.timestamp)
        object.__setattr__(self, "symbol", self.symbol.upper())
        for field_name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, field_name, money(getattr(self, field_name)))


@dataclass(frozen=True)
class MarketDataSnapshot:
    symbol: str
    last_price: Decimal
    timestamp: datetime
    average_volume: Decimal | None = None
    average_traded_value: Decimal | None = None
    bid_ask_spread_fraction: Decimal | None = None
    recent_activity: bool | None = None
    estimated_price_impact_fraction: Decimal | None = None
    abnormal_volatility: bool | None = None

    def __post_init__(self) -> None:
        require_aware(self.timestamp)
        object.__setattr__(self, "symbol", self.symbol.upper())
        for field_name in (
            "last_price",
            "average_volume",
            "average_traded_value",
            "bid_ask_spread_fraction",
            "estimated_price_impact_fraction",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, money(value))

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        require_aware(now, "now")
        return self.timestamp > now or now - self.timestamp > max_age


@dataclass(frozen=True)
class TradeProposal:
    decision_id: str
    symbol: str
    side: TradeSide
    proposed_price: Decimal
    strategy: str = "manual"
    quantity: int | None = None
    timestamp: datetime | None = None
    signal_type: SignalType | None = None
    asset_class: AssetClass = AssetClass.INDIAN_EQUITY
    confidence: Decimal | None = None
    market_regime: MarketRegime | None = None
    key_signals: tuple[str, ...] = field(default_factory=tuple)
    relevant_features: dict[str, Any] = field(default_factory=dict)
    stop_or_invalidation_level: Decimal | None = None
    summary: str = ""

    def __post_init__(self) -> None:
        if self.timestamp is not None:
            require_aware(self.timestamp)
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "proposed_price", money(self.proposed_price))
        if self.quantity is not None and self.quantity < 0:
            raise FailClosedError("quantity cannot be negative")
        if self.signal_type is None:
            mapped = {
                TradeSide.BUY: SignalType.BUY,
                TradeSide.SELL: SignalType.SELL,
                TradeSide.HOLD: SignalType.HOLD,
            }[self.side]
            object.__setattr__(self, "signal_type", mapped)

    @classmethod
    def buy(cls, symbol: str, price: Decimal, decision_id: str, quantity: int | None = None, **kwargs: Any) -> "TradeProposal":
        return cls(decision_id=decision_id, symbol=symbol, side=TradeSide.BUY, proposed_price=price, quantity=quantity, **kwargs)

    @classmethod
    def sell(cls, symbol: str, price: Decimal, decision_id: str, quantity: int | None = None, **kwargs: Any) -> "TradeProposal":
        return cls(decision_id=decision_id, symbol=symbol, side=TradeSide.SELL, proposed_price=price, quantity=quantity, **kwargs)

    @classmethod
    def hold(cls, symbol: str, price: Decimal, decision_id: str, **kwargs: Any) -> "TradeProposal":
        return cls(decision_id=decision_id, symbol=symbol, side=TradeSide.HOLD, proposed_price=price, quantity=0, **kwargs)


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: Decimal = money("0")
    exchange_fees: Decimal = money("0")
    taxes: Decimal = money("0")
    stamp_duty: Decimal = money("0")
    other: Decimal = money("0")
    schedule_version: str = "unspecified"

    @property
    def total(self) -> Decimal:
        return self.brokerage + self.exchange_fees + self.taxes + self.stamp_duty + self.other


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    decision_id: str
    symbol: str
    side: TradeSide
    quantity: int = 0
    estimated_costs: Decimal = money("0")
    gross_trade_value: Decimal = money("0")
    capital_required: Decimal = money("0")
    rejection_reason: str | None = None
    risk_assessment: str = ""

    @property
    def approval_status(self) -> ApprovalStatus:
        return ApprovalStatus.APPROVED if self.approved else ApprovalStatus.REJECTED


@dataclass
class Position:
    symbol: str
    quantity: int
    average_price: Decimal

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper()
        self.average_price = money(self.average_price)
        if self.quantity < 0:
            raise FailClosedError("long-only positions cannot be negative")

    def market_value(self, price: Decimal) -> Decimal:
        return money(price) * self.quantity


@dataclass(frozen=True)
class OrderExecution:
    order_id: str
    decision_id: str
    idempotency_key: str
    symbol: str
    side: TradeSide
    quantity: int
    execution_price: Decimal
    gross_value: Decimal
    transaction_costs: Decimal
    net_cash_flow: Decimal
    timestamp: datetime | None
    status: str
    rejection_reason: str | None = None
    slippage: Decimal = money("0")

    def __post_init__(self) -> None:
        if self.timestamp is not None:
            require_aware(self.timestamp)
