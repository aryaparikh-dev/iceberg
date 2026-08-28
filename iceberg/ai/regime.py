from __future__ import annotations

from decimal import Decimal

from iceberg.domain.enums import MarketRegime
from iceberg.domain.models import Candle


class RegimeDetector:
    """Transparent statistical regime detector. It is advisory only."""

    def detect(self, history: tuple[Candle, ...] | list[Candle]) -> MarketRegime:
        if len(history) < 3:
            return MarketRegime.SIDEWAYS
        first = history[0].close
        last = history[-1].close
        if first <= 0:
            return MarketRegime.SIDEWAYS
        change = (last - first) / first
        ranges = [(c.high - c.low) / c.close for c in history if c.close > 0]
        avg_range = sum(ranges) / Decimal(len(ranges)) if ranges else Decimal("0")
        if avg_range > Decimal("0.05"):
            return MarketRegime.HIGH_VOLATILITY
        if avg_range < Decimal("0.005"):
            return MarketRegime.LOW_VOLATILITY
        if change > Decimal("0.05"):
            return MarketRegime.STRONG_BULL
        if change > Decimal("0.01"):
            return MarketRegime.WEAK_BULL
        if change < Decimal("-0.10"):
            return MarketRegime.PANIC
        if change < Decimal("-0.03"):
            return MarketRegime.BEAR
        return MarketRegime.SIDEWAYS
