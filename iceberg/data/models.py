from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from iceberg.domain.models import Candle, money, require_aware
from iceberg.exceptions import FailClosedError


IST = ZoneInfo("Asia/Kolkata")


class DataQualityStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class AdjustmentMode(str, Enum):
    RAW = "RAW"
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"
    TOTAL_RETURN_ADJUSTED = "TOTAL_RETURN_ADJUSTED"


class CorporateActionStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE = "AVAILABLE"
    APPLIED = "APPLIED"


class CorporateActionType(str, Enum):
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    DIVIDEND = "DIVIDEND"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    MERGER = "MERGER"
    DELISTING = "DELISTING"


class IssueSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class HistoricalBar:
    symbol: str
    exchange: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    interval: str
    source_id: str
    ingested_at: datetime
    trading_date: date | None = None
    timezone: str = "Asia/Kolkata"
    adjustment_mode: AdjustmentMode = AdjustmentMode.RAW
    corporate_action_status: CorporateActionStatus = CorporateActionStatus.UNKNOWN

    def __post_init__(self) -> None:
        require_aware(self.timestamp)
        require_aware(self.ingested_at, "ingested_at")
        local = self.timestamp.astimezone(IST)
        resolved_trading_date = self.trading_date or local.date()
        if resolved_trading_date != local.date():
            raise FailClosedError("trading_date must match timestamp in Asia/Kolkata")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "exchange", self.exchange.upper())
        object.__setattr__(self, "timestamp", local)
        object.__setattr__(self, "ingested_at", self.ingested_at.astimezone(IST))
        object.__setattr__(self, "trading_date", resolved_trading_date)
        object.__setattr__(self, "timezone", "Asia/Kolkata")
        object.__setattr__(self, "adjustment_mode", AdjustmentMode(self.adjustment_mode))
        object.__setattr__(self, "corporate_action_status", CorporateActionStatus(self.corporate_action_status))
        for field_name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, field_name, money(getattr(self, field_name)))

    def to_candle(self) -> Candle:
        return Candle(
            symbol=self.symbol,
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["ingested_at"] = self.ingested_at.isoformat()
        data["trading_date"] = self.trading_date.isoformat() if self.trading_date else None
        data["open"] = str(self.open)
        data["high"] = str(self.high)
        data["low"] = str(self.low)
        data["close"] = str(self.close)
        data["volume"] = str(self.volume)
        data["adjustment_mode"] = self.adjustment_mode.value
        data["corporate_action_status"] = self.corporate_action_status.value
        return data


@dataclass(frozen=True)
class InstrumentMetadata:
    symbol: str
    exchange: str = "NSE"
    series: str = "EQ"
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    listing_date: date | None = None
    delisting_date: date | None = None
    tradable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "exchange", self.exchange.upper())
        object.__setattr__(self, "series", self.series.upper())

    def is_tradable_on(self, trading_date: date) -> bool:
        if not self.tradable:
            return False
        if self.series != "EQ":
            return False
        if self.listing_date is not None and trading_date < self.listing_date:
            return False
        if self.delisting_date is not None and trading_date > self.delisting_date:
            return False
        return True


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    action_type: CorporateActionType
    ex_date: date
    ratio: Decimal | None = None
    cash_amount: Decimal | None = None
    new_symbol: str | None = None
    source_reference: str = ""
    verified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "action_type", CorporateActionType(self.action_type))
        if self.ratio is not None:
            object.__setattr__(self, "ratio", money(self.ratio))
        if self.cash_amount is not None:
            object.__setattr__(self, "cash_amount", money(self.cash_amount))
        if self.new_symbol is not None:
            object.__setattr__(self, "new_symbol", self.new_symbol.upper())


@dataclass(frozen=True)
class MarketDataMetadata:
    source: str
    source_identifier: str
    ingestion_time: datetime
    original_filename: str | None
    checksum_sha256: str | None
    symbol: str
    exchange: str
    interval: str
    start_date: date | None
    end_date: date | None
    adjustment_mode: AdjustmentMode
    adjustment_methodology: str
    corporate_action_status: CorporateActionStatus

    def __post_init__(self) -> None:
        require_aware(self.ingestion_time, "ingestion_time")
        object.__setattr__(self, "ingestion_time", self.ingestion_time.astimezone(IST))
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "exchange", self.exchange.upper())
        object.__setattr__(self, "adjustment_mode", AdjustmentMode(self.adjustment_mode))
        object.__setattr__(self, "corporate_action_status", CorporateActionStatus(self.corporate_action_status))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ingestion_time"] = self.ingestion_time.isoformat()
        data["start_date"] = self.start_date.isoformat() if self.start_date else None
        data["end_date"] = self.end_date.isoformat() if self.end_date else None
        data["adjustment_mode"] = self.adjustment_mode.value
        data["corporate_action_status"] = self.corporate_action_status.value
        return data


@dataclass(frozen=True)
class DataIssue:
    code: str
    severity: IssueSeverity
    symbol: str | None = None
    timestamp: datetime | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DataQualityReport:
    symbol: str
    start_date: date | None
    end_date: date | None
    number_of_bars: int
    duplicates: int = 0
    missing_bars: int = 0
    missing_sessions: int = 0
    ohlc_errors: int = 0
    timezone_errors: int = 0
    outlier_jumps: int = 0
    zero_volume_bars: int = 0
    corporate_action_warnings: int = 0
    quality_status: DataQualityStatus = DataQualityStatus.PASS
    issues: tuple[DataIssue, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "quality_status", DataQualityStatus(self.quality_status))

    @property
    def passed(self) -> bool:
        return self.quality_status is DataQualityStatus.PASS

    @property
    def failed(self) -> bool:
        return self.quality_status is DataQualityStatus.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "number_of_bars": self.number_of_bars,
            "duplicates": self.duplicates,
            "missing_bars": self.missing_bars,
            "missing_sessions": self.missing_sessions,
            "ohlc_errors": self.ohlc_errors,
            "timezone_errors": self.timezone_errors,
            "outlier_jumps": self.outlier_jumps,
            "zero_volume_bars": self.zero_volume_bars,
            "corporate_action_warnings": self.corporate_action_warnings,
            "quality_status": self.quality_status.value,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class NormalizedDataset:
    bars: tuple[HistoricalBar, ...]
    metadata: MarketDataMetadata
    quality_report: DataQualityReport

    def candles_by_symbol(self) -> dict[str, list[Candle]]:
        grouped: dict[str, list[Candle]] = {}
        for bar in self.bars:
            grouped.setdefault(bar.symbol, []).append(bar.to_candle())
        return grouped
