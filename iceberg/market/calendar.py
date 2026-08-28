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


class VerifiedTradingCalendar(TradingCalendar):
    def __init__(self, known_holidays: set[date] | None = None) -> None:
        super().__init__(known_holidays=known_holidays or set(), provider_verified=True)


class StaticBacktestCalendar(TradingCalendar):
    def __init__(self, trading_days: set[date] | None = None, known_holidays: set[date] | None = None) -> None:
        super().__init__(known_holidays=known_holidays or set(), provider_verified=True)
        self.trading_days = trading_days

    def is_trading_day(self, trading_date: date) -> bool:
        if self.trading_days is not None:
            return trading_date in self.trading_days and trading_date not in self.known_holidays
        return super().is_trading_day(trading_date)


class UnknownTradingCalendar(TradingCalendar):
    def __init__(self) -> None:
        super().__init__(known_holidays=set(), provider_verified=False)
