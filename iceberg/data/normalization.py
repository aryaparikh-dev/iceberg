from __future__ import annotations

from dataclasses import replace
from zoneinfo import ZoneInfo

from iceberg.data.models import HistoricalBar, IST


def normalize_to_ist(bars: list[HistoricalBar] | tuple[HistoricalBar, ...]) -> tuple[HistoricalBar, ...]:
    normalized = []
    for bar in bars:
        local = bar.timestamp.astimezone(IST)
        normalized.append(replace(bar, timestamp=local, trading_date=local.date(), timezone="Asia/Kolkata"))
    return tuple(normalized)


def convert_timezone(bars: list[HistoricalBar] | tuple[HistoricalBar, ...], timezone: str = "Asia/Kolkata") -> tuple[HistoricalBar, ...]:
    target = ZoneInfo(timezone)
    converted = []
    for bar in bars:
        timestamp = bar.timestamp.astimezone(target)
        converted.append(replace(bar, timestamp=timestamp, trading_date=timestamp.astimezone(IST).date()))
    return tuple(converted)
