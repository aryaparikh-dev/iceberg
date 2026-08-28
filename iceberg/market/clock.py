from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from iceberg.config.settings import MarketSettings
from iceberg.domain.models import require_aware
from iceberg.market.calendar import TradingCalendar


@dataclass
class MarketClock:
    calendar: TradingCalendar
    settings: MarketSettings

    def to_market_time(self, timestamp: datetime) -> datetime:
        require_aware(timestamp)
        return timestamp.astimezone(self.settings.zoneinfo)

    def is_market_open(self, timestamp: datetime) -> bool:
        local = self.to_market_time(timestamp)
        if not self.calendar.is_trading_day(local.date()):
            return False
        return self.settings.market_open <= local.time() <= self.settings.normal_market_close

    def can_open_new_position(self, timestamp: datetime) -> bool:
        local = self.to_market_time(timestamp)
        return self.is_market_open(local) and self.settings.new_entries_start <= local.time() <= self.settings.last_new_entry_time

    def is_force_exit_window(self, timestamp: datetime) -> bool:
        local = self.to_market_time(timestamp)
        return self.is_market_open(local) and self.settings.force_exit_start <= local.time() <= self.settings.force_exit_deadline

    def force_exit_deadline_passed(self, timestamp: datetime) -> bool:
        local = self.to_market_time(timestamp)
        return self.calendar.is_trading_day(local.date()) and local.time() > self.settings.force_exit_deadline
