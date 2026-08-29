from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from decimal import Decimal

from iceberg.domain.models import Candle, require_aware
from iceberg.data.models import DataIssue, DataQualityReport, DataQualityStatus, HistoricalBar, IssueSeverity
from iceberg.market.clock import MarketClock
from iceberg.market.calendar import TradingCalendar


class DataValidationError(Exception):
    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or reason)


@dataclass
class DataValidator:
    max_staleness: timedelta

    def validate_candles(self, candles: list[Candle] | tuple[Candle, ...], *, expected_symbol: str, now: datetime) -> None:
        require_aware(now, "now")
        if not candles:
            raise DataValidationError("MISSING_DATA")
        previous = None
        seen = set()
        for candle in candles:
            if candle.symbol != expected_symbol.upper():
                raise DataValidationError("SYMBOL_MISMATCH")
            if candle.timestamp > now:
                raise DataValidationError("FUTURE_TIMESTAMP")
            if candle.timestamp in seen:
                raise DataValidationError("DUPLICATE_CANDLE")
            seen.add(candle.timestamp)
            if previous is not None and candle.timestamp < previous:
                raise DataValidationError("NON_MONOTONIC_TIMESTAMPS")
            previous = candle.timestamp
            if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
                raise DataValidationError("NON_POSITIVE_PRICE")
            if candle.high < candle.low:
                raise DataValidationError("HIGH_LESS_THAN_LOW")
            if not candle.low <= candle.open <= candle.high:
                raise DataValidationError("OPEN_OUTSIDE_RANGE")
            if not candle.low <= candle.close <= candle.high:
                raise DataValidationError("CLOSE_OUTSIDE_RANGE")
            if candle.volume < 0:
                raise DataValidationError("INVALID_VOLUME")
        latest = candles[-1].timestamp
        if now - latest > self.max_staleness:
            raise DataValidationError("STALE_DATA")


@dataclass(frozen=True)
class DataQualityRules:
    interval: timedelta = timedelta(minutes=1)
    max_price_jump_fraction: Decimal = Decimal("0.50")
    allow_zero_volume: bool = False
    require_regular_spacing: bool = True
    symbol_pattern: str = r"^[A-Z0-9&.-]{1,20}$"


class HistoricalDataQualityValidator:
    def __init__(
        self,
        *,
        market_clock: MarketClock,
        calendar: TradingCalendar,
        rules: DataQualityRules | None = None,
    ) -> None:
        self.market_clock = market_clock
        self.calendar = calendar
        self.rules = rules or DataQualityRules()

    def validate(self, bars: list[HistoricalBar] | tuple[HistoricalBar, ...], *, symbol: str) -> DataQualityReport:
        expected_symbol = symbol.upper()
        issues: list[DataIssue] = []
        duplicates = 0
        missing_bars = 0
        missing_sessions = 0
        ohlc_errors = 0
        timezone_errors = 0
        outlier_jumps = 0
        zero_volume_bars = 0
        timestamps: set[datetime] = set()
        previous: HistoricalBar | None = None
        sessions_seen: set[date] = set()

        if not bars:
            issues.append(DataIssue("MISSING_DATA", IssueSeverity.ERROR, expected_symbol, detail="no bars supplied"))

        for bar in bars:
            if bar.symbol != expected_symbol:
                issues.append(DataIssue("SYMBOL_MISMATCH", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if not re.match(self.rules.symbol_pattern, bar.symbol):
                issues.append(DataIssue("MALFORMED_SYMBOL", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            try:
                require_aware(bar.timestamp)
            except Exception:
                timezone_errors += 1
                issues.append(DataIssue("TIMEZONE_NAIVE", IssueSeverity.ERROR, bar.symbol, detail="timestamp lacks timezone"))
            if str(bar.timestamp.tzinfo) != "Asia/Kolkata":
                timezone_errors += 1
                issues.append(DataIssue("NON_IST_TIMESTAMP", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if bar.timestamp > datetime.now(tz=bar.timestamp.tzinfo):
                issues.append(DataIssue("FUTURE_TIMESTAMP", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if not self.market_clock.is_market_open(bar.timestamp):
                issues.append(DataIssue("OUT_OF_SESSION", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if bar.timestamp in timestamps:
                duplicates += 1
                issues.append(DataIssue("DUPLICATE_TIMESTAMP", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            timestamps.add(bar.timestamp)
            sessions_seen.add(bar.trading_date)
            if previous is not None:
                if bar.timestamp <= previous.timestamp:
                    issues.append(DataIssue("NON_MONOTONIC_TIMESTAMPS", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
                if self.rules.require_regular_spacing:
                    expected = previous.timestamp + self.rules.interval
                    if bar.trading_date == previous.trading_date and bar.timestamp != expected:
                        missing = max(0, int((bar.timestamp - expected) / self.rules.interval))
                        missing_bars += missing or 1
                        issues.append(DataIssue("INCONSISTENT_INTERVAL_SPACING", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
                if previous.close > 0:
                    jump = abs(bar.close - previous.close) / previous.close
                    if jump > self.rules.max_price_jump_fraction:
                        outlier_jumps += 1
                        issues.append(DataIssue("IMPOSSIBLE_PRICE_JUMP", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
                ohlc_errors += 1
                issues.append(DataIssue("NON_POSITIVE_PRICE", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if bar.high < bar.low or not bar.low <= bar.open <= bar.high or not bar.low <= bar.close <= bar.high:
                ohlc_errors += 1
                issues.append(DataIssue("INVALID_OHLC_RELATIONSHIP", IssueSeverity.ERROR, bar.symbol, bar.timestamp))
            if bar.volume < 0 or (bar.volume == 0 and not self.rules.allow_zero_volume):
                zero_volume_bars += 1
                severity = IssueSeverity.ERROR if bar.volume < 0 else IssueSeverity.WARNING
                issues.append(DataIssue("ZERO_OR_NEGATIVE_VOLUME", severity, bar.symbol, bar.timestamp))
            previous = bar

        if bars:
            first_date = min(bar.trading_date for bar in bars)
            last_date = max(bar.trading_date for bar in bars)
            day = first_date
            while day <= last_date:
                if self.calendar.is_trading_day(day) and day not in sessions_seen:
                    missing_sessions += 1
                    issues.append(DataIssue("MISSING_TRADING_SESSION", IssueSeverity.ERROR, expected_symbol, detail=day.isoformat()))
                day += timedelta(days=1)
        else:
            first_date = None
            last_date = None

        errors = [issue for issue in issues if issue.severity is IssueSeverity.ERROR]
        warnings = [issue for issue in issues if issue.severity is IssueSeverity.WARNING]
        status = DataQualityStatus.FAIL if errors else DataQualityStatus.WARNING if warnings else DataQualityStatus.PASS
        return DataQualityReport(
            symbol=expected_symbol,
            start_date=first_date,
            end_date=last_date,
            number_of_bars=len(bars),
            duplicates=duplicates,
            missing_bars=missing_bars,
            missing_sessions=missing_sessions,
            ohlc_errors=ohlc_errors,
            timezone_errors=timezone_errors,
            outlier_jumps=outlier_jumps,
            zero_volume_bars=zero_volume_bars,
            corporate_action_warnings=sum(1 for issue in issues if issue.code.startswith("CORPORATE_ACTION")),
            quality_status=status,
            issues=tuple(issues),
        )
