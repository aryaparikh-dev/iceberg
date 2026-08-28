from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from iceberg.domain.enums import MarketRegime
from iceberg.domain.models import Candle, TradeProposal
from iceberg.strategies.base import Strategy


class MomentumStrategy(Strategy):
    name = "momentum"
    methodology = "indicator-rules"

    def __init__(self, lookback: int = 3) -> None:
        self.lookback = lookback

    def generate(self, symbol: str, history: tuple[Candle, ...], now: datetime, regime: MarketRegime) -> list[TradeProposal]:
        if len(history) < self.lookback:
            return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]
        recent = history[-self.lookback :]
        if recent[-1].close > recent[0].close:
            return [TradeProposal.buy(symbol, recent[-1].close, f"{self.name}-buy-{now.isoformat()}", timestamp=now, strategy=self.name)]
        return [TradeProposal.hold(symbol, recent[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]


class TrendFollowingStrategy(Strategy):
    name = "trend_following"
    methodology = "indicator-rules"

    def generate(self, symbol: str, history: tuple[Candle, ...], now: datetime, regime: MarketRegime) -> list[TradeProposal]:
        if len(history) < 5:
            return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]
        short = sum(c.close for c in history[-3:]) / Decimal("3")
        long = sum(c.close for c in history[-5:]) / Decimal("5")
        if short > long:
            return [TradeProposal.buy(symbol, history[-1].close, f"{self.name}-buy-{now.isoformat()}", timestamp=now, strategy=self.name)]
        return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"
    methodology = "statistics-rules"

    def generate(self, symbol: str, history: tuple[Candle, ...], now: datetime, regime: MarketRegime) -> list[TradeProposal]:
        if len(history) < 5:
            return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]
        average = sum(c.close for c in history[-5:]) / Decimal("5")
        if history[-1].close < average * Decimal("0.98"):
            return [TradeProposal.buy(symbol, history[-1].close, f"{self.name}-buy-{now.isoformat()}", timestamp=now, strategy=self.name)]
        return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]


class BreakoutStrategy(Strategy):
    name = "breakout"
    methodology = "indicator-rules"

    def __init__(self, lookback: int = 5) -> None:
        self.lookback = lookback

    def generate(self, symbol: str, history: tuple[Candle, ...], now: datetime, regime: MarketRegime) -> list[TradeProposal]:
        if len(history) <= self.lookback:
            return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]
        previous_high = max(c.high for c in history[-self.lookback - 1 : -1])
        if history[-1].close > previous_high:
            return [TradeProposal.buy(symbol, history[-1].close, f"{self.name}-buy-{now.isoformat()}", timestamp=now, strategy=self.name)]
        return [TradeProposal.hold(symbol, history[-1].close, f"{self.name}-hold-{now.isoformat()}", timestamp=now, strategy=self.name)]
