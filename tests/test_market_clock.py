from datetime import date

from iceberg.market.calendar import TradingCalendar
from iceberg.market.clock import MarketClock

from tests.conftest import ist_datetime


def test_market_clock_uses_ist_and_normal_session(settings):
    clock = MarketClock(TradingCalendar(known_holidays=set(), provider_verified=True), settings.market)

    assert clock.is_market_open(ist_datetime(9, 15))
    assert clock.is_market_open(ist_datetime(15, 30))
    assert not clock.is_market_open(ist_datetime(9, 14))
    assert not clock.is_market_open(ist_datetime(15, 31))


def test_calendar_rejects_weekends_holidays_and_unknown_provider(settings):
    holiday = date(2026, 1, 5)
    calendar = TradingCalendar(known_holidays={holiday}, provider_verified=True)
    assert not calendar.is_trading_day(holiday)
    assert not calendar.is_trading_day(date(2026, 1, 4))

    unknown = TradingCalendar(known_holidays=set(), provider_verified=False)
    assert unknown.market_state_known() is False
    assert not unknown.is_trading_day(holiday)
