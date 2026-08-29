from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable

from iceberg.backtesting.engine import BacktestEngine, BacktestReport
from iceberg.data.universe import UniverseSelection
from iceberg.domain.models import Candle
from iceberg.strategies.base import Strategy


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"{type(value)!r} is not JSON serializable")


@dataclass(frozen=True)
class ExperimentConfig:
    strategy_name: str
    strategy_version: str
    parameters: dict
    universe: str
    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    bar_interval: str
    initial_capital: Decimal
    transaction_cost_schedule: str
    slippage_model: str
    adjustment_mode: str
    data_checksums: dict[str, str] = field(default_factory=dict)
    random_seed: int | None = None
    code_commit_sha: str | None = None

    def reproducible_id(self) -> str:
        payload = json.dumps(asdict(self), default=_json_default, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def manifest(self) -> dict:
        payload = asdict(self)
        payload["experiment_id"] = self.reproducible_id()
        return json.loads(json.dumps(payload, default=_json_default, sort_keys=True))


def current_git_commit_sha(cwd: str | Path = ".") -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, check=True, capture_output=True, text=True)
    except Exception:
        return None
    return result.stdout.strip()


def save_experiment_manifest(config: ExperimentConfig, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.manifest(), indent=2, sort_keys=True))


class ExperimentRunner:
    def __init__(self, engine_factory: Callable[[], BacktestEngine]) -> None:
        self.engine_factory = engine_factory

    def run_one(self, candles_by_symbol: dict[str, list[Candle]], strategy: Strategy) -> BacktestReport:
        return self.engine_factory().run(candles_by_symbol, strategy)

    def compare(
        self,
        candles_by_symbol: dict[str, list[Candle]],
        strategies: list[Strategy] | tuple[Strategy, ...],
    ) -> dict[str, BacktestReport]:
        results: dict[str, BacktestReport] = {}
        for strategy in strategies:
            results[strategy.name] = self.run_one(candles_by_symbol, strategy)
        return results


def config_from_selection(
    *,
    strategy: Strategy,
    selection: UniverseSelection,
    start_date: date,
    end_date: date,
    bar_interval: str,
    initial_capital: Decimal,
    transaction_cost_schedule: str,
    slippage_model: str,
    adjustment_mode: str,
    parameters: dict | None = None,
    data_checksums: dict[str, str] | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        strategy_name=strategy.name,
        strategy_version=getattr(strategy, "version", "unversioned"),
        parameters=parameters or {},
        universe=selection.name,
        symbols=selection.symbols,
        start_date=start_date,
        end_date=end_date,
        bar_interval=bar_interval,
        initial_capital=initial_capital,
        transaction_cost_schedule=transaction_cost_schedule,
        slippage_model=slippage_model,
        adjustment_mode=adjustment_mode,
        data_checksums=data_checksums or {},
    )
