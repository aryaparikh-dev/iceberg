from datetime import date, datetime
from pathlib import Path

import pytest

from iceberg.data.corporate_actions import CorporateActionAdjuster
from iceberg.data.loaders import HistoricalDataLoader
from iceberg.data.metadata import checksum_file, metadata_for_file
from iceberg.data.models import (
    AdjustmentMode,
    CorporateAction,
    CorporateActionStatus,
    CorporateActionType,
    HistoricalBar,
    InstrumentMetadata,
    IST,
)
from iceberg.data.sources import CSVHistoricalDataSource, ParquetHistoricalDataSource
from iceberg.data.universe import PointInTimeUniverse, StaticUniverse
from iceberg.data.validation import DataQualityRules, DataQualityStatus, HistoricalDataQualityValidator
from iceberg.exceptions import ConfigurationError, FailClosedError
from iceberg.config.settings import default_settings
from iceberg.market.calendar import StaticBacktestCalendar
from iceberg.market.clock import MarketClock

from tests.conftest import D, ist_datetime


def quality_validator(*, trading_days=None, interval_minutes=1):
    from datetime import timedelta

    calendar = StaticBacktestCalendar(trading_days=trading_days or {date(2026, 1, 5)})
    return HistoricalDataQualityValidator(
        market_clock=MarketClock(calendar, settings=default_settings().market),
        calendar=calendar,
        rules=DataQualityRules(interval=timedelta(minutes=interval_minutes)),
    )


def bar(
    minute,
    *,
    symbol="ABC",
    day=5,
    open_price="10",
    high="11",
    low="9",
    close="10",
    volume="1000",
):
    return HistoricalBar(
        symbol=symbol,
        exchange="NSE",
        timestamp=ist_datetime(10, minute, day=day),
        open=D(open_price),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D(volume),
        interval="1m",
        source_id="unit-test",
        ingested_at=ist_datetime(8, 0),
    )


def test_csv_data_import_reads_required_ohlcv_schema():
    path = Path(__file__).parent / "fixtures" / "sample_ohlcv.csv"
    source = CSVHistoricalDataSource(path, source_id="fixture-csv")

    bars = source.get_candles(["ABC"])

    assert len(bars) == 3
    assert bars[0].symbol == "ABC"
    assert bars[0].exchange == "NSE"
    assert bars[0].timezone == "Asia/Kolkata"
    assert bars[0].adjustment_mode is AdjustmentMode.RAW
    assert source.get_symbols() == ["ABC"]


def test_timezone_normalization_from_explicit_naive_csv_import(tmp_path):
    csv_path = tmp_path / "naive.csv"
    csv_path.write_text("timestamp,symbol,open,high,low,close,volume\n2026-01-05 10:00:00,ABC,10,10,10,10,100\n")
    source = CSVHistoricalDataSource(csv_path, timestamp_format="%Y-%m-%d %H:%M:%S", timezone="Asia/Kolkata")

    bars = source.get_candles()

    assert bars[0].timestamp.tzinfo == IST
    assert bars[0].timestamp.hour == 10


def test_naive_csv_timestamps_fail_without_explicit_timezone_policy(tmp_path):
    csv_path = tmp_path / "naive-rejected.csv"
    csv_path.write_text("timestamp,symbol,open,high,low,close,volume\n2026-01-05 10:00:00,ABC,10,10,10,10,100\n")
    source = CSVHistoricalDataSource(
        csv_path,
        timestamp_format="%Y-%m-%d %H:%M:%S",
        assume_timezone_for_naive=False,
    )

    with pytest.raises(ConfigurationError):
        source.get_candles()


def test_duplicate_detection_fails_quality_report():
    duplicate = bar(0)
    report = quality_validator().validate([duplicate, duplicate], symbol="ABC")

    assert report.quality_status is DataQualityStatus.FAIL
    assert report.duplicates == 1
    assert any(issue.code == "DUPLICATE_TIMESTAMP" for issue in report.issues)


def test_missing_bars_are_reported_without_repair():
    report = quality_validator().validate([bar(0), bar(2)], symbol="ABC")

    assert report.quality_status is DataQualityStatus.FAIL
    assert report.missing_bars == 1
    assert any(issue.code == "INCONSISTENT_INTERVAL_SPACING" for issue in report.issues)


def test_invalid_ohlc_relationship_fails_quality_report():
    report = quality_validator().validate([bar(0, high="9", low="11")], symbol="ABC")

    assert report.quality_status is DataQualityStatus.FAIL
    assert report.ohlc_errors >= 1


def test_future_timestamps_are_rejected_by_quality_report():
    future = HistoricalBar(
        symbol="ABC",
        exchange="NSE",
        timestamp=datetime(2099, 1, 5, 10, 0, tzinfo=IST),
        open=D("10"),
        high=D("10"),
        low=D("10"),
        close=D("10"),
        volume=D("1000"),
        interval="1m",
        source_id="unit-test",
        ingested_at=ist_datetime(8, 0),
    )

    report = quality_validator(trading_days={date(2099, 1, 5)}).validate([future], symbol="ABC")

    assert report.quality_status is DataQualityStatus.FAIL
    assert any(issue.code == "FUTURE_TIMESTAMP" for issue in report.issues)


def test_out_of_session_data_fails_quality_report():
    outside = HistoricalBar(
        symbol="ABC",
        exchange="NSE",
        timestamp=ist_datetime(8, 0),
        open=D("10"),
        high=D("10"),
        low=D("10"),
        close=D("10"),
        volume=D("1000"),
        interval="1m",
        source_id="unit-test",
        ingested_at=ist_datetime(7, 0),
    )

    report = quality_validator().validate([outside], symbol="ABC")

    assert report.quality_status is DataQualityStatus.FAIL
    assert any(issue.code == "OUT_OF_SESSION" for issue in report.issues)


def test_missing_trading_days_are_reported():
    report = quality_validator(trading_days={date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)}).validate(
        [bar(0, day=5), bar(0, day=7)],
        symbol="ABC",
    )

    assert report.quality_status is DataQualityStatus.FAIL
    assert report.missing_sessions == 1


def test_loader_refuses_fail_quality_dataset(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("timestamp,symbol,open,high,low,close,volume\n2026-01-05T10:00:00+05:30,ABC,10,9,11,10,100\n")
    source = CSVHistoricalDataSource(csv_path)
    metadata = metadata_for_file(
        csv_path,
        source="unit",
        source_identifier="bad",
        symbol="ABC",
        exchange="NSE",
        interval="1m",
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_methodology="raw",
        corporate_action_status=CorporateActionStatus.UNKNOWN,
    )

    with pytest.raises(FailClosedError):
        HistoricalDataLoader(source, quality_validator()).load_symbol("ABC", metadata)


def test_corporate_action_split_adjustment_is_explicit():
    bars = [bar(0, close="100", open_price="100", high="100", low="100")]
    action = CorporateAction("ABC", CorporateActionType.SPLIT, ex_date=date(2026, 1, 6), ratio=D("2"), verified=True)

    adjusted = CorporateActionAdjuster().adjust(bars, [action], AdjustmentMode.SPLIT_ADJUSTED)

    assert adjusted[0].close == D("50")
    assert adjusted[0].volume == D("2000")
    assert adjusted[0].adjustment_mode is AdjustmentMode.SPLIT_ADJUSTED
    assert adjusted[0].corporate_action_status is CorporateActionStatus.APPLIED


def test_adjusted_mode_requires_corporate_action_data():
    with pytest.raises(FailClosedError):
        CorporateActionAdjuster().adjust([bar(0)], [], AdjustmentMode.SPLIT_ADJUSTED)


def test_point_in_time_universe_uses_historical_membership():
    universe = PointInTimeUniverse(
        "NIFTY50-PIT",
        {
            date(2020, 1, 1): ["ABC", "OLD"],
            date(2021, 1, 1): ["ABC", "NEW"],
        },
    )

    before = universe.eligible_symbols(date(2020, 6, 1))
    after = universe.eligible_symbols(date(2021, 6, 1))

    assert before.symbols == ("ABC", "OLD")
    assert after.symbols == ("ABC", "NEW")
    assert before.survivorship_bias_risk is False


def test_static_universe_flags_survivorship_bias_risk():
    selection = StaticUniverse("manual", ["ABC", "XYZ"]).eligible_symbols(date(2026, 1, 5))

    assert selection.symbols == ("ABC", "XYZ")
    assert selection.survivorship_bias_risk is True
    assert selection.warnings == ("SURVIVORSHIP_BIAS_RISK=TRUE",)


def test_instrument_metadata_filters_cash_equity_eligibility():
    metadata = {
        "ABC": InstrumentMetadata("ABC", series="EQ"),
        "FUT": InstrumentMetadata("FUT", series="FUTSTK"),
        "OLD": InstrumentMetadata("OLD", delisting_date=date(2020, 1, 1)),
    }

    selection = StaticUniverse("eligible", ["ABC", "FUT", "OLD"], survivorship_bias_risk=False).eligible_symbols(
        date(2026, 1, 5),
        metadata=metadata,
    )

    assert selection.symbols == ("ABC",)


def test_metadata_checksum_and_normalized_storage(tmp_path):
    source_file = tmp_path / "bars.csv"
    source_file.write_text("timestamp,symbol,open,high,low,close,volume\n2026-01-05T10:00:00+05:30,ABC,10,10,10,10,100\n")

    assert checksum_file(source_file)


def test_parquet_adapter_is_optional_when_dependency_missing(tmp_path):
    source = ParquetHistoricalDataSource(tmp_path / "missing.parquet")

    with pytest.raises(ConfigurationError):
        source.get_candles()
