from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import median

from iceberg.data.models import HistoricalBar
from iceberg.domain.models import money, require_aware


@dataclass(frozen=True)
class LiquiditySnapshot:
    symbol: str
    as_of: datetime
    average_daily_volume: Decimal | None
    average_traded_value: Decimal | None
    rolling_median_volume: Decimal | None
    observed_volume: Decimal | None
    max_participation_rate: Decimal
    lookback_bars: int

    def max_quantity_for_observed_volume(self) -> int | None:
        if self.observed_volume is None:
            return None
        return int((self.observed_volume * self.max_participation_rate).to_integral_value())


class HistoricalLiquidityModel:
    def __init__(self, *, lookback_bars: int = 20, max_participation_rate: Decimal = Decimal("0.01")) -> None:
        if lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")
        self.lookback_bars = lookback_bars
        self.max_participation_rate = money(max_participation_rate)

    def snapshot(self, bars: list[HistoricalBar] | tuple[HistoricalBar, ...], *, symbol: str, as_of: datetime) -> LiquiditySnapshot:
        require_aware(as_of, "as_of")
        symbol = symbol.upper()
        available = [bar for bar in bars if bar.symbol == symbol and bar.timestamp <= as_of]
        available = sorted(available, key=lambda bar: bar.timestamp)
        lookback = available[-self.lookback_bars :]
        volumes = [bar.volume for bar in lookback]
        traded_values = [bar.close * bar.volume for bar in lookback]
        observed = available[-1].volume if available else None
        return LiquiditySnapshot(
            symbol=symbol,
            as_of=as_of,
            average_daily_volume=None if not volumes else sum(volumes, Decimal("0")) / Decimal(len(volumes)),
            average_traded_value=None if not traded_values else sum(traded_values, Decimal("0")) / Decimal(len(traded_values)),
            rolling_median_volume=None if not volumes else money(str(median(volumes))),
            observed_volume=observed,
            max_participation_rate=self.max_participation_rate,
            lookback_bars=len(lookback),
        )
