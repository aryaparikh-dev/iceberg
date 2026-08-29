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


@dataclass(frozen=True)
class VolumeParticipationSlippageModel(SlippageModel):
    observed_volume: Decimal
    base_basis_points: Decimal = Decimal("0")
    participation_basis_points: Decimal = Decimal("100")

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_volume", money(self.observed_volume))
        object.__setattr__(self, "base_basis_points", money(self.base_basis_points))
        object.__setattr__(self, "participation_basis_points", money(self.participation_basis_points))

    def execution_price(self, side: TradeSide, reference_price: Decimal, quantity: int) -> Decimal:
        if self.observed_volume <= 0:
            raise ValueError("observed volume must be positive for participation slippage")
        participation = Decimal(quantity) / self.observed_volume
        bps = self.base_basis_points + participation * self.participation_basis_points
        return FixedBpsSlippageModel(bps).execution_price(side, reference_price, quantity)


@dataclass(frozen=True)
class VolatilityAwareSlippageModel(SlippageModel):
    volatility_fraction: Decimal
    base_basis_points: Decimal = Decimal("0")
    volatility_multiplier: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        object.__setattr__(self, "volatility_fraction", money(self.volatility_fraction))
        object.__setattr__(self, "base_basis_points", money(self.base_basis_points))
        object.__setattr__(self, "volatility_multiplier", money(self.volatility_multiplier))

    def execution_price(self, side: TradeSide, reference_price: Decimal, quantity: int) -> Decimal:
        bps = self.base_basis_points + self.volatility_fraction * self.volatility_multiplier * Decimal("10000")
        return FixedBpsSlippageModel(bps).execution_price(side, reference_price, quantity)
