from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from iceberg.domain.models import MarketDataSnapshot


@dataclass(frozen=True)
class SimulatedLiquidityAssumptionProfile:
    average_volume: Decimal
    average_traded_value: Decimal
    bid_ask_spread_fraction: Decimal
    estimated_price_impact_fraction: Decimal
    recent_activity: bool = True
    abnormal_volatility: bool = False
    name: str = "explicit-simulated-liquidity"


class BacktestMarketDataAdapter:
    def __init__(self, liquidity_assumptions: SimulatedLiquidityAssumptionProfile | None = None) -> None:
        self.liquidity_assumptions = liquidity_assumptions

    @property
    def uses_simulated_liquidity(self) -> bool:
        return self.liquidity_assumptions is not None

    def snapshot(self, symbol: str, price: Decimal, timestamp: datetime) -> MarketDataSnapshot:
        if self.liquidity_assumptions is None:
            return MarketDataSnapshot(symbol=symbol, last_price=price, timestamp=timestamp)
        profile = self.liquidity_assumptions
        return MarketDataSnapshot(
            symbol=symbol,
            last_price=price,
            timestamp=timestamp,
            average_volume=profile.average_volume,
            average_traded_value=profile.average_traded_value,
            bid_ask_spread_fraction=profile.bid_ask_spread_fraction,
            recent_activity=profile.recent_activity,
            estimated_price_impact_fraction=profile.estimated_price_impact_fraction,
            abnormal_volatility=profile.abnormal_volatility,
        )
