from __future__ import annotations

from dataclasses import replace

from iceberg.data.models import DataQualityStatus, MarketDataMetadata, NormalizedDataset
from iceberg.data.normalization import normalize_to_ist
from iceberg.data.sources.base import HistoricalMarketDataSource
from iceberg.data.validation import HistoricalDataQualityValidator
from iceberg.exceptions import FailClosedError


class HistoricalDataLoader:
    def __init__(self, source: HistoricalMarketDataSource, validator: HistoricalDataQualityValidator) -> None:
        self.source = source
        self.validator = validator

    def load_symbol(self, symbol: str, metadata: MarketDataMetadata, *, reject_failures: bool = True) -> NormalizedDataset:
        bars = normalize_to_ist(self.source.get_candles([symbol]))
        if bars:
            metadata = replace(
                metadata,
                start_date=min(bar.trading_date for bar in bars),
                end_date=max(bar.trading_date for bar in bars),
                adjustment_mode=bars[0].adjustment_mode,
                corporate_action_status=bars[0].corporate_action_status,
            )
        report = self.validator.validate(list(bars), symbol=symbol)
        if reject_failures and report.quality_status is DataQualityStatus.FAIL:
            raise FailClosedError(f"data quality failed for {symbol}: {report.issues[0].code if report.issues else 'UNKNOWN'}")
        return NormalizedDataset(bars=bars, metadata=metadata, quality_report=report)
