# Market Data

Phase 3 uses local, legally obtained historical data only. The code does not scrape, download, or endorse unlicensed market-data collection.

## Storage Layout

Market data is separated by lifecycle:

- `data/raw/`: original files exactly as supplied by the user or vendor.
- `data/normalized/`: validated, normalized files generated from raw inputs.
- `data/derived/`: research outputs derived from normalized data.
- `data/cache/` and `data/experiments/`: local working artifacts.

Large data directories are ignored by Git. Small deterministic fixtures may live under `tests/fixtures/`.

## Required OHLCV Schema

CSV import expects these canonical columns unless an explicit column mapping is supplied by code:

```text
timestamp,symbol,open,high,low,close,volume
```

Every normalized bar records symbol, exchange, timestamp, Asia/Kolkata timezone, trading date, interval, source identifier, ingestion timestamp, adjustment mode, and corporate-action status.

Timestamps must be timezone-aware after import. Naive CSV timestamps are accepted only when the caller explicitly supplies the import timezone; otherwise ingestion fails.

## Data Quality

`HistoricalDataQualityValidator` creates a `DataQualityReport` with `PASS`, `WARNING`, or `FAIL`.

It flags duplicate timestamps, non-monotonic timestamps, missing bars, missing sessions, invalid OHLC relationships, negative prices, zero or negative volume, malformed symbols, timezone errors, out-of-session bars, future timestamps, impossible price jumps, and inconsistent interval spacing.

Suspicious data is not automatically repaired. Backtests should refuse `FAIL` datasets.

## Corporate Actions

Supported adjustment modes are:

- `RAW`
- `SPLIT_ADJUSTED`
- `TOTAL_RETURN_ADJUSTED`

The corporate-action layer represents splits, bonus issues, dividends, symbol changes, mergers, and delistings. Adjusted modes require explicit corporate-action data. If actions are unavailable, the system raises or reports that limitation instead of silently mixing adjusted and unadjusted series.

## Universes

Use `StaticUniverse` for manually supplied lists and `PointInTimeUniverse` for historical membership. Static universes default to `SURVIVORSHIP_BIAS_RISK=TRUE`; point-in-time universes can represent additions and removals over time.

Instrument metadata supports symbol, exchange, series, ISIN, sector, industry, listing date, delisting date, and tradable status. V1 remains Indian cash equity, long-only.

## Providers

`HistoricalMarketDataSource` is the adapter boundary. Local `CSVHistoricalDataSource` works without internet access. `ParquetHistoricalDataSource` is optional and requires local pandas/pyarrow support when used. Future commercial or exchange data providers should be implemented as adapters behind the same interface.
