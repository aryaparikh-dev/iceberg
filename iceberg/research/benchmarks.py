from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from iceberg.domain.models import Candle, money


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    start_date: date | None
    end_date: date | None
    total_return: Decimal
    maximum_drawdown: Decimal
    cagr: Decimal | None = None
    metric_unavailable_reasons: dict[str, str] | None = None


class CashBenchmark:
    name = "cash"

    def evaluate(self, *, start_date: date | None = None, end_date: date | None = None) -> BenchmarkResult:
        return BenchmarkResult(self.name, start_date, end_date, money("0"), money("0"), None, {"cagr": "cash benchmark has no market exposure"})


class BuyAndHoldBenchmark:
    def __init__(self, name: str = "buy_and_hold") -> None:
        self.name = name

    def evaluate(self, candles: list[Candle] | tuple[Candle, ...]) -> BenchmarkResult:
        if len(candles) < 2:
            return BenchmarkResult(self.name, None, None, money("0"), money("0"), None, {"return": "insufficient benchmark bars"})
        ordered = sorted(candles, key=lambda candle: candle.timestamp)
        start = ordered[0].close
        end = ordered[-1].close
        total_return = money("0") if start == 0 else (end - start) / start
        equity = [candle.close / start for candle in ordered if start]
        drawdown = _max_drawdown(equity)
        return BenchmarkResult(self.name, ordered[0].timestamp.date(), ordered[-1].timestamp.date(), total_return, drawdown)


def _max_drawdown(equity_curve: list[Decimal]) -> Decimal:
    if not equity_curve:
        return money("0")
    peak = equity_curve[0]
    drawdown = money("0")
    for value in equity_curve:
        peak = max(peak, value)
        if peak:
            drawdown = max(drawdown, (peak - value) / peak)
    return drawdown
