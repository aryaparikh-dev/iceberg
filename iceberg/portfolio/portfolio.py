from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from iceberg.domain.models import Position, money
from iceberg.exceptions import CapitalInvariantError, FailClosedError


@dataclass
class Portfolio:
    positions: dict[str, Position] = field(default_factory=dict)

    def record_buy(self, symbol: str, quantity: int, execution_price: Decimal) -> None:
        symbol = symbol.upper()
        if quantity <= 0:
            raise FailClosedError("buy quantity must be positive")
        price = money(execution_price)
        current = self.positions.get(symbol)
        if current is None:
            self.positions[symbol] = Position(symbol, quantity, price)
            return
        total_qty = current.quantity + quantity
        total_cost = current.average_price * current.quantity + price * quantity
        current.quantity = total_qty
        current.average_price = total_cost / total_qty

    def record_sell(self, symbol: str, quantity: int, execution_price: Decimal) -> Decimal:
        symbol = symbol.upper()
        if quantity <= 0:
            raise FailClosedError("sell quantity must be positive")
        current = self.positions.get(symbol)
        if current is None or current.quantity < quantity:
            raise CapitalInvariantError("cannot sell more than the long-only position")
        basis = current.average_price * quantity
        current.quantity -= quantity
        if current.quantity == 0:
            del self.positions[symbol]
        return basis

    def exposure(self, symbol: str, mark_price: Decimal | None = None) -> Decimal:
        position = self.positions.get(symbol.upper())
        if position is None:
            return money("0")
        price = money(mark_price) if mark_price is not None else position.average_price
        return position.market_value(price)

    def total_market_value(self, prices: dict[str, Decimal] | None = None) -> Decimal:
        total = money("0")
        prices = prices or {}
        for symbol, position in self.positions.items():
            total += position.market_value(prices.get(symbol, position.average_price))
        return total

    def is_flat(self) -> bool:
        return not self.positions
