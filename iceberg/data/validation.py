from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from iceberg.domain.models import Candle, require_aware


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
