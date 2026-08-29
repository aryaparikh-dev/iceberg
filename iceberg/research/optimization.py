from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from iceberg.research.walk_forward import TimeRange


@dataclass(frozen=True)
class ParameterAttempt:
    parameters: dict
    train_metrics: dict
    accepted: bool
    rejection_reason: str | None = None


@dataclass(frozen=True)
class OptimizationResult:
    attempts: tuple[ParameterAttempt, ...]
    best_parameters: dict | None
    objective: str
    constraints: dict = field(default_factory=dict)
    train_only: bool = True


class GridSearch:
    def __init__(self, parameter_grid: dict[str, list]) -> None:
        self.parameter_grid = parameter_grid

    def candidates(self) -> list[dict]:
        keys = list(self.parameter_grid)
        return [dict(zip(keys, values)) for values in itertools.product(*(self.parameter_grid[key] for key in keys))]

    def run(
        self,
        evaluator: Callable[[dict, TimeRange], dict],
        *,
        train_range: TimeRange,
        objective: str,
        constraints: dict | None = None,
    ) -> OptimizationResult:
        return _select_best(self.candidates(), evaluator, train_range=train_range, objective=objective, constraints=constraints or {})


class RandomSearch:
    def __init__(self, parameter_space: dict[str, list], *, attempts: int, seed: int) -> None:
        self.parameter_space = parameter_space
        self.attempts = attempts
        self.seed = seed

    def candidates(self) -> list[dict]:
        rng = random.Random(self.seed)
        keys = list(self.parameter_space)
        return [{key: rng.choice(self.parameter_space[key]) for key in keys} for _ in range(self.attempts)]

    def run(
        self,
        evaluator: Callable[[dict, TimeRange], dict],
        *,
        train_range: TimeRange,
        objective: str,
        constraints: dict | None = None,
    ) -> OptimizationResult:
        return _select_best(self.candidates(), evaluator, train_range=train_range, objective=objective, constraints=constraints or {})


def _select_best(
    candidates: list[dict],
    evaluator: Callable[[dict, TimeRange], dict],
    *,
    train_range: TimeRange,
    objective: str,
    constraints: dict,
) -> OptimizationResult:
    attempts: list[ParameterAttempt] = []
    best_parameters = None
    best_score = None
    for parameters in candidates:
        metrics = evaluator(parameters, train_range)
        rejection = _constraint_rejection(metrics, constraints)
        accepted = rejection is None
        attempts.append(ParameterAttempt(parameters, metrics, accepted, rejection))
        score = metrics.get(objective)
        if accepted and score is not None and (best_score is None or Decimal(str(score)) > best_score):
            best_score = Decimal(str(score))
            best_parameters = parameters
    return OptimizationResult(tuple(attempts), best_parameters, objective, constraints, train_only=True)


def _constraint_rejection(metrics: dict, constraints: dict) -> str | None:
    min_trades = constraints.get("minimum_trades")
    if min_trades is not None and metrics.get("trades", 0) < min_trades:
        return "minimum_trades"
    max_drawdown = constraints.get("maximum_drawdown")
    if max_drawdown is not None and metrics.get("maximum_drawdown") is not None:
        if Decimal(str(metrics["maximum_drawdown"])) > Decimal(str(max_drawdown)):
            return "maximum_drawdown"
    min_duration = constraints.get("minimum_test_duration_days")
    if min_duration is not None and metrics.get("duration_days", 0) < min_duration:
        return "minimum_test_duration_days"
    return None
