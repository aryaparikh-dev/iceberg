from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from iceberg.domain.enums import TradeSide
from iceberg.domain.models import money


class SlippageModel(ABC):
    @abstractmethod
    def execution_price(self, side: TradeSide, reference_price: Decimal, quantity: int) -> Decimal:
        raise NotImplementedError


@dataclass(frozen=True)
class FixedBpsSlippageModel(SlippageModel):
    basis_points: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "basis_points", money(self.basis_points))

    def execution_price(self, side: TradeSide, reference_price: Decimal, quantity: int) -> Decimal:
        adjustment = self.basis_points / Decimal("10000")
        if side is TradeSide.BUY:
            return money(reference_price) * (Decimal("1") + adjustment)
        if side is TradeSide.SELL:
            return money(reference_price) * (Decimal("1") - adjustment)
        return money(reference_price)


class VolumeAwareSlippageModel(SlippageModel):
    def execution_price(self, side: TradeSide, reference_price: Decimal, quantity: int) -> Decimal:
        raise NotImplementedError("volume-aware slippage requires explicit market-depth data")
