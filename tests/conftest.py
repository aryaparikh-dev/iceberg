from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from iceberg.capital.guard import CapitalGuard
from iceberg.config.settings import default_settings
from iceberg.domain.models import MarketDataSnapshot
from iceberg.market.calendar import TradingCalendar
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import FixedTransactionCostModel
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.engine import RiskEngine
from iceberg.risk.permissions import PermissionManager


IST = ZoneInfo("Asia/Kolkata")
TRADING_DATE = date(2026, 1, 5)


def D(value: str | int) -> Decimal:
    return Decimal(str(value))


def ist_datetime(hour: int, minute: int = 0, second: int = 0, *, day: int = 5) -> datetime:
    return datetime(2026, 1, day, hour, minute, second, tzinfo=IST)


def market_snapshot(symbol: str, price: str | int, now: datetime | None = None, **overrides) -> MarketDataSnapshot:
    now = now or ist_datetime(10, 0)
    defaults = {
        "symbol": symbol,
        "last_price": D(price),
        "timestamp": now,
        "average_volume": D("100000"),
        "average_traded_value": D("10000000"),
        "bid_ask_spread_fraction": D("0.001"),
        "recent_activity": True,
        "estimated_price_impact_fraction": D("0.001"),
        "abnormal_volatility": False,
    }
    defaults.update(overrides)
    return MarketDataSnapshot(**defaults)


@pytest.fixture
def settings():
    return default_settings()


@pytest.fixture
def safe_context(settings):
    calendar = TradingCalendar(known_holidays=set(), provider_verified=True)
    clock = MarketClock(calendar=calendar, settings=settings.market)
    guard = CapitalGuard.initial(D("100"), settings=settings)
    guard.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 0))
    portfolio = Portfolio()
    permissions = PermissionManager.default_ai()
    emergency_stop = EmergencyStop(active=False)
    cost_model = FixedTransactionCostModel()
    risk = RiskEngine(settings=settings, cost_model=cost_model)
    return SimpleNamespace(
        settings=settings,
        calendar=calendar,
        clock=clock,
        guard=guard,
        portfolio=portfolio,
        permissions=permissions,
        emergency_stop=emergency_stop,
        cost_model=cost_model,
        risk=risk,
        now=ist_datetime(10, 0),
    )
