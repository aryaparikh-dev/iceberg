from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from iceberg.domain.enums import StrategyLifecycle


@dataclass
class StrategyEvaluationMetrics:
    maximum_drawdown: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal
    win_rate: Decimal
    average_win: Decimal
    average_loss: Decimal
    turnover: Decimal
    tail_risk: Decimal
    regime_performance: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class CandidateStrategy:
    name: str
    lifecycle: StrategyLifecycle = StrategyLifecycle.CANDIDATE
    automatic_deployment_allowed: bool = False

    def promote(self, target: StrategyLifecycle, *, human_approved: bool = False) -> None:
        if target in {StrategyLifecycle.APPROVED, StrategyLifecycle.LIVE_ELIGIBLE} and not human_approved:
            raise PermissionError("human approval is required for approval or live eligibility")
        self.lifecycle = target
