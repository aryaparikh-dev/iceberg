from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from iceberg.data.models import CorporateAction, HistoricalBar, InstrumentMetadata
from iceberg.data.sources.base import HistoricalMarketDataSource
from iceberg.exceptions import ConfigurationError
from iceberg.market.calendar import StaticBacktestCalendar


class ParquetHistoricalDataSource(HistoricalMarketDataSource):
    """Local Parquet adapter using pandas/pyarrow when those optional packages exist."""

    def __init__(
        self,
        paths: str | Path | list[str | Path],
        *,
        source_id: str = "local-parquet",
        csv_compatible_options: dict | None = None,
    ) -> None:
        if isinstance(paths, (str, Path)):
            paths = [paths]
        self.paths = [Path(path) for path in paths]
        self.source_id = source_id
        self.csv_compatible_options = csv_compatible_options or {}

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
        missing = [str(path) for path in self.paths if not path.exists()]
        if missing:
            raise ConfigurationError(f"Parquet source file not found: {', '.join(missing)}")
        try:
            import pandas as pd
        except ImportError as exc:
            raise ConfigurationError("ParquetHistoricalDataSource requires optional pandas/pyarrow support") from exc

        rows = []
        for path in self.paths:
            frame = pd.read_parquet(path)
            rows.extend(frame.to_dict("records"))
        adapter = _ParquetRowAdapter(rows, source_id=self.source_id, **self.csv_compatible_options)
        return adapter.get_candles(symbols=symbols, start=start, end=end, interval=interval)

    def get_trading_calendar(self) -> StaticBacktestCalendar:
        return StaticBacktestCalendar(trading_days={bar.trading_date for bar in self.get_candles()})

    def get_instrument_metadata(self, symbols: list[str] | None = None) -> dict[str, InstrumentMetadata]:
        wanted = {symbol.upper() for symbol in symbols} if symbols is not None else set(self.get_symbols())
        return {symbol: InstrumentMetadata(symbol=symbol) for symbol in wanted}

    def get_corporate_actions(self, symbols: list[str] | None = None) -> list[CorporateAction]:
        return []


class _ParquetRowAdapter:
    def __init__(self, rows: list[dict], **options) -> None:
        self.rows = rows
        self.options = options
        self.source_id = options.get("source_id", "local-parquet")

    def get_candles(
        self,
        symbols: list[str] | None = None,
        *,
        start: date | None = None,
        end: date | None = None,
        interval: str | None = None,
    ) -> list[HistoricalBar]:
        from iceberg.data.sources.csv_source import CSVHistoricalDataSource

        source = CSVHistoricalDataSource([], **self.options)
        wanted = {symbol.upper() for symbol in symbols} if symbols is not None else None
        bars = []
        for row in self.rows:
            normalized = {key: _stringify(value) for key, value in row.items()}
            bar = source._row_to_bar(normalized)
            if wanted is not None and bar.symbol not in wanted:
                continue
            if start is not None and bar.trading_date < start:
                continue
            if end is not None and bar.trading_date > end:
                continue
            if interval is not None and bar.interval != interval:
                continue
            bars.append(bar)
        return bars


def _stringify(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
