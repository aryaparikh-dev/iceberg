from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from iceberg.domain.enums import TradingMode
from iceberg.domain.models import money


@dataclass
class MarketSettings:
    timezone: str = "Asia/Kolkata"
    market_open: time = time(9, 15)
    new_entries_start: time = time(9, 15)
    last_new_entry_time: time = time(15, 10)
    force_exit_start: time = time(15, 20)
    force_exit_deadline: time = time(15, 25)
    normal_market_close: time = time(15, 30)

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass
class CapitalSettings:
    initial_capital_inr: Decimal = money("100")
    maximum_stock_allocation: Decimal = money("0.10")
    maximum_portfolio_allocation: Decimal = money("1.00")
    leverage_allowed: bool = False
    fractional_shares_allowed: bool = False
    intraday_capital_topups_allowed: bool = False


@dataclass
class RiskSettings:
    daily_loss_limit_fraction: Decimal = money("0.20")
    max_consecutive_losses: int = 3
    maximum_positions: int = 10
    min_average_volume: Decimal = money("1000")
    min_average_traded_value: Decimal = money("100000")
    max_bid_ask_spread_fraction: Decimal = money("0.02")
    max_estimated_price_impact_fraction: Decimal = money("0.01")
    emergency_stop_enabled: bool = True


@dataclass
class TestingSettings:
    paper_trading_enabled: bool = True
    live_trading_enabled: bool = False
    trading_mode: TradingMode = TradingMode.FULLY_AUTOMATED_PAPER


@dataclass
class SafetySettings:
    withdrawals_allowed: bool = False
    bank_account_access_allowed: bool = False
    external_transfers_allowed: bool = False
    fail_closed: bool = True


@dataclass
class SettlementSettings:
    profit_sharing_enabled: bool = True
    profit_sharing_threshold: Decimal = money("0.10")
    user_profit_fraction_above_threshold: Decimal = money("0.50")
    paper_settlement_lag_days: int = 1


@dataclass
class DataSettings:
    max_market_data_age: timedelta = timedelta(minutes=5)


@dataclass
class LearningSettings:
    strategy_discovery: bool = True
    strategy_optimization: bool = True
    automatic_strategy_deployment: bool = False


@dataclass
class Settings:
    market: MarketSettings = field(default_factory=MarketSettings)
    capital: CapitalSettings = field(default_factory=CapitalSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    testing: TestingSettings = field(default_factory=TestingSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    settlement: SettlementSettings = field(default_factory=SettlementSettings)
    data: DataSettings = field(default_factory=DataSettings)
    learning: LearningSettings = field(default_factory=LearningSettings)


def default_settings() -> Settings:
    return Settings()
