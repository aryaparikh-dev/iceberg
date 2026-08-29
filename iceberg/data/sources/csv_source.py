from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from iceberg.data.models import (
    AdjustmentMode,
    CorporateAction,
    CorporateActionStatus,
    HistoricalBar,
    InstrumentMetadata,
    IST,
)
from iceberg.data.sources.base import HistoricalMarketDataSource
from iceberg.exceptions import ConfigurationError
from iceberg.market.calendar import StaticBacktestCalendar


DEFAULT_COLUMN_MAPPING = {
    "timestamp": "timestamp",
    "symbol": "symbol",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


class CSVHistoricalDataSource(HistoricalMarketDataSource):
    def __init__(
        self,
        paths: str | Path | list[str | Path],
        *,
        source_id: str = "local-csv",
        exchange: str = "NSE",
        interval: str = "1m",
        column_mapping: dict[str, str] | None = None,
        timestamp_format: str | None = None,
        timezone: str = "Asia/Kolkata",
        assume_timezone_for_naive: bool = True,
        adjustment_mode: AdjustmentMode = AdjustmentMode.RAW,
        corporate_action_status: CorporateActionStatus = CorporateActionStatus.UNKNOWN,
        ingested_at: datetime | None = None,
        metadata: dict[str, InstrumentMetadata] | None = None,
        corporate_actions: list[CorporateAction] | None = None,
    ) -> None:
        if isinstance(paths, (str, Path)):
            paths = [paths]
        self.paths = [Path(path) for path in paths]
        self.source_id = source_id
        self.exchange = exchange
        self.interval = interval
        self.column_mapping = column_mapping or DEFAULT_COLUMN_MAPPING
        self.timestamp_format = timestamp_format
        self.timezone = ZoneInfo(timezone)
        self.assume_timezone_for_naive = assume_timezone_for_naive
        self.adjustment_mode = AdjustmentMode(adjustment_mode)
        self.corporate_action_status = CorporateActionStatus(corporate_action_status)
        self.ingested_at = ingested_at or datetime.now(tz=IST)
        self._metadata = {symbol.upper(): value for symbol, value in (metadata or {}).items()}
        self._corporate_actions = corporate_actions or []

    def get_symbols(self) -> list[str]:
        return sorted({bar.symbol for bar in self.get_candles()})

    def get_candles(
        self,
        symbols: list[str] | None = None,
        *,
        start: date | None = None,
        end: date | None = None,
        interval: str | None = None,
    ) -> list[HistoricalBar]:
        wanted = {symbol.upper() for symbol in symbols} if symbols is not None else None
        bars: list[HistoricalBar] = []
        for path in self.paths:
            bars.extend(self._read_file(path))
        filtered = []
        for bar in bars:
            if wanted is not None and bar.symbol not in wanted:
                continue
            if start is not None and bar.trading_date < start:
                continue
            if end is not None and bar.trading_date > end:
                continue
            if interval is not None and bar.interval != interval:
                continue
            filtered.append(bar)
        return filtered

    def get_trading_calendar(self) -> StaticBacktestCalendar:
        return StaticBacktestCalendar(trading_days={bar.trading_date for bar in self.get_candles()})

    def get_instrument_metadata(self, symbols: list[str] | None = None) -> dict[str, InstrumentMetadata]:
        wanted = {symbol.upper() for symbol in symbols} if symbols is not None else set(self.get_symbols())
        result = {}
        for symbol in wanted:
            result[symbol] = self._metadata.get(symbol, InstrumentMetadata(symbol=symbol, exchange=self.exchange))
        return result

    def get_corporate_actions(self, symbols: list[str] | None = None) -> list[CorporateAction]:
        wanted = {symbol.upper() for symbol in symbols} if symbols is not None else None
        return [action for action in self._corporate_actions if wanted is None or action.symbol in wanted]

    def _read_file(self, path: Path) -> list[HistoricalBar]:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            self._validate_mapping(reader.fieldnames or [], path)
            return [self._row_to_bar(row) for row in reader]

    def _validate_mapping(self, fieldnames: list[str], path: Path) -> None:
        missing = [source for source in self.column_mapping.values() if source not in fieldnames]
        if missing:
            raise ConfigurationError(f"CSV source {path} missing columns: {', '.join(missing)}")

    def _row_to_bar(self, row: dict[str, str]) -> HistoricalBar:
        mapped = {canonical: row[source] for canonical, source in self.column_mapping.items()}
        timestamp = self._parse_timestamp(mapped["timestamp"])
        return HistoricalBar(
            symbol=mapped["symbol"],
            exchange=self.exchange,
            timestamp=timestamp,
            open=Decimal(mapped["open"]),
            high=Decimal(mapped["high"]),
            low=Decimal(mapped["low"]),
            close=Decimal(mapped["close"]),
            volume=Decimal(mapped["volume"]),
            interval=self.interval,
            source_id=self.source_id,
            ingested_at=self.ingested_at,
            adjustment_mode=self.adjustment_mode,
            corporate_action_status=self.corporate_action_status,
        )

    def _parse_timestamp(self, value: str) -> datetime:
        timestamp = datetime.strptime(value, self.timestamp_format) if self.timestamp_format else datetime.fromisoformat(value)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            if not self.assume_timezone_for_naive:
                raise ConfigurationError("CSV timestamp is timezone-naive and no explicit import timezone was allowed")
            timestamp = timestamp.replace(tzinfo=self.timezone)
        return timestamp.astimezone(IST)
