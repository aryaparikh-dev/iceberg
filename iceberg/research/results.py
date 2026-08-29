from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"{type(value)!r} is not JSON serializable")


@dataclass(frozen=True)
class TradeLedgerEntry:
    trade_id: str
    decision_id: str
    symbol: str
    strategy: str
    entry_signal_timestamp: datetime | None
    entry_execution_timestamp: datetime | None
    entry_price: Decimal
    quantity: int
    entry_costs: Decimal
    exit_signal_timestamp: datetime | None
    exit_execution_timestamp: datetime | None
    exit_price: Decimal
    exit_costs: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    return_percentage: Decimal | None
    holding_duration_seconds: int | None
    exit_reason: str
    market_regime: str | None
    slippage: Decimal
    capital_at_entry: Decimal | None
    position_allocation_percentage: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), default=_json_default))


@dataclass(frozen=True)
class DailyEquityPoint:
    trading_date: date
    starting_capital: Decimal
    gross_pnl: Decimal
    transaction_costs: Decimal
    slippage: Decimal
    net_pnl: Decimal
    distribution: Decimal
    ending_ai_capital: Decimal
    drawdown: Decimal

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), default=_json_default))


@dataclass(frozen=True)
class BacktestMetricSummary:
    gross_profit: Decimal
    net_profit: Decimal
    largest_win: Decimal | None
    largest_loss: Decimal | None
    capital_utilization: Decimal | None
    average_holding_time_seconds: Decimal | None
    exposure_time_fraction: Decimal | None
    turnover: Decimal | None
    metric_unavailable_reasons: dict[str, str] = field(default_factory=dict)


def export_trade_ledger_csv(entries: list[TradeLedgerEntry] | tuple[TradeLedgerEntry, ...], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(TradeLedgerEntry.__dataclass_fields__)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_dict())


def export_trade_ledger_json(entries: list[TradeLedgerEntry] | tuple[TradeLedgerEntry, ...], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([entry.to_dict() for entry in entries], indent=2, sort_keys=True))


def export_daily_equity_json(points: list[DailyEquityPoint] | tuple[DailyEquityPoint, ...], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([point.to_dict() for point in points], indent=2, sort_keys=True))
