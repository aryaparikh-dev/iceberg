from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class OverfittingDiagnostics:
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


class OverfittingDiagnosticEngine:
    def evaluate(
        self,
        *,
        total_trades: int,
        train_return: Decimal | None = None,
        test_return: Decimal | None = None,
        parameter_attempts: int = 0,
        symbols: dict[str, int] | None = None,
        period_returns: list[Decimal] | None = None,
    ) -> OverfittingDiagnostics:
        warnings: list[str] = []
        if total_trades < 20:
            warnings.append("VERY_FEW_TRADES")
        if train_return is not None and test_return is not None and abs(train_return - test_return) > Decimal("0.50"):
            warnings.append("TRAIN_TEST_PERFORMANCE_GAP")
        if parameter_attempts > max(20, total_trades * 2):
            warnings.append("EXCESSIVE_PARAMETER_SEARCH")
        if symbols:
            top_symbol_trades = max(symbols.values())
            if total_trades and Decimal(top_symbol_trades) / Decimal(total_trades) > Decimal("0.50"):
                warnings.append("ONE_STOCK_DEPENDENCE")
        if period_returns and len(period_returns) > 1:
            positive = any(value > 0 for value in period_returns)
            negative = any(value < 0 for value in period_returns)
            if positive and negative and max(period_returns) - min(period_returns) > Decimal("0.50"):
                warnings.append("UNSTABLE_PERIOD_PERFORMANCE")
        return OverfittingDiagnostics(tuple(warnings))
