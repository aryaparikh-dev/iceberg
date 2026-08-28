from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo
import tomllib

from iceberg.domain.enums import TradingMode
from iceberg.domain.models import money
from iceberg.exceptions import ConfigurationError


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


def validate_settings(settings: Settings) -> Settings:
    if settings.capital.maximum_stock_allocation > money("0.10"):
        raise ConfigurationError("maximum_stock_allocation cannot exceed 0.10 in V1")
    if settings.capital.maximum_portfolio_allocation > money("1.00"):
        raise ConfigurationError("maximum_portfolio_allocation cannot exceed 1.00 in V1")
    if settings.capital.leverage_allowed:
        raise ConfigurationError("leverage is disabled in V1")
    if settings.capital.fractional_shares_allowed:
        raise ConfigurationError("fractional shares are disabled in V1")
    if settings.capital.intraday_capital_topups_allowed:
        raise ConfigurationError("intraday capital topups are disabled in V1")
    if settings.testing.live_trading_enabled:
        raise ConfigurationError("live trading is disabled in V1")
    if settings.testing.trading_mode is TradingMode.FULLY_AUTOMATED_LIVE:
        raise ConfigurationError("fully automated live trading is unavailable in V1")
    if settings.safety.withdrawals_allowed:
        raise ConfigurationError("withdrawals are disabled in V1")
    if settings.safety.bank_account_access_allowed:
        raise ConfigurationError("bank access is disabled in V1")
    if settings.safety.external_transfers_allowed:
        raise ConfigurationError("external transfers are disabled in V1")
    return settings


def default_settings() -> Settings:
    return validate_settings(Settings())


def load_settings(path: str | Path | None = None) -> Settings:
    if path is None:
        candidate = Path(__file__).resolve().parents[2] / "config" / "defaults.toml"
        if not candidate.exists():
            return default_settings()
        path = candidate
    data = tomllib.loads(Path(path).read_text())
    settings = Settings()
    _apply_toml(settings, data)
    return validate_settings(settings)


def _apply_toml(settings: Settings, data: dict) -> None:
    market = data.get("market", {})
    for key in ("timezone",):
        if key in market:
            setattr(settings.market, key, market[key])
    for key in ("market_open", "new_entries_start", "last_new_entry_time", "force_exit_start", "force_exit_deadline", "normal_market_close"):
        if key in market:
            setattr(settings.market, key, _parse_time(market[key]))

    capital = data.get("capital", {})
    for key in ("initial_capital_inr", "maximum_stock_allocation", "maximum_portfolio_allocation"):
        if key in capital:
            setattr(settings.capital, key, money(capital[key]))
    for key in ("leverage_allowed", "fractional_shares_allowed", "intraday_capital_topups_allowed"):
        if key in capital:
            setattr(settings.capital, key, bool(capital[key]))

    risk = data.get("risk", {})
    for key in ("daily_loss_limit_fraction",):
        if key in risk:
            setattr(settings.risk, key, money(risk[key]))
    for key in ("max_consecutive_losses", "maximum_positions"):
        if key in risk:
            setattr(settings.risk, key, int(risk[key]))

    testing = data.get("testing", {})
    if "paper_trading_enabled" in testing:
        settings.testing.paper_trading_enabled = bool(testing["paper_trading_enabled"])
    if "live_trading_enabled" in testing:
        settings.testing.live_trading_enabled = bool(testing["live_trading_enabled"])
    if "trading_mode" in testing:
        settings.testing.trading_mode = TradingMode(testing["trading_mode"])

    safety = data.get("safety", {})
    for key in ("withdrawals_allowed", "bank_account_access_allowed", "external_transfers_allowed", "fail_closed"):
        if key in safety:
            setattr(settings.safety, key, bool(safety[key]))

    settlement = data.get("settlement", {})
    for key in ("profit_sharing_threshold", "user_profit_fraction_above_threshold"):
        if key in settlement:
            setattr(settings.settlement, key, money(settlement[key]))
    if "paper_settlement_lag_days" in settlement:
        settings.settlement.paper_settlement_lag_days = int(settlement["paper_settlement_lag_days"])

    learning = data.get("learning", {})
    for key in ("strategy_discovery", "strategy_optimization", "automatic_strategy_deployment"):
        if key in learning:
            setattr(settings.learning, key, bool(learning[key]))


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


class ReadOnlySettings:
    def __init__(self, wrapped) -> None:
        object.__setattr__(self, "_wrapped", wrapped)

    def __getattr__(self, name: str):
        value = getattr(self._wrapped, name)
        if hasattr(value, "__dataclass_fields__"):
            return ReadOnlySettings(value)
        if isinstance(value, dict):
            return MappingProxyType(value)
        return value

    def __setattr__(self, name: str, value) -> None:
        raise ConfigurationError("strategy settings are read-only")


def settings_for_strategy(settings: Settings) -> ReadOnlySettings:
    return ReadOnlySettings(settings)
