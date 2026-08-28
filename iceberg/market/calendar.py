from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class TradingCalendar:
    known_holidays: set[date] = field(default_factory=set)
    provider_verified: bool = False

    def market_state_known(self) -> bool:
        return self.provider_verified

    def is_trading_day(self, trading_date: date) -> bool:
        if not self.market_state_known():
            return False
        if trading_date.weekday() >= 5:
            return False
        if trading_date in self.known_holidays:
            return False
        return True
