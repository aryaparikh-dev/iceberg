from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


class AssetClass(StrEnum):
    INDIAN_EQUITY = "INDIAN_EQUITY"


class OrderStatus(StrEnum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


class ApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Permission(StrEnum):
    MARKET_DATA_READ = "MARKET_DATA_READ"
    PORTFOLIO_READ = "PORTFOLIO_READ"
    PAPER_TRADE = "PAPER_TRADE"
    LIVE_TRADE = "LIVE_TRADE"
    WITHDRAW_FUNDS = "WITHDRAW_FUNDS"
    BANK_ACCESS = "BANK_ACCESS"
    EXTERNAL_TRANSFER = "EXTERNAL_TRANSFER"
    CAPITAL_ADMIN = "CAPITAL_ADMIN"
    FUNDING_CONFIRM = "FUNDING_CONFIRM"


class FundingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    APPLIED = "APPLIED"


class TradingMode(StrEnum):
    FULLY_AUTOMATED_PAPER = "FULLY_AUTOMATED_PAPER"
    HUMAN_APPROVAL_LIVE = "HUMAN_APPROVAL_LIVE"
    FULLY_AUTOMATED_LIVE = "FULLY_AUTOMATED_LIVE"


class MarketRegime(StrEnum):
    STRONG_BULL = "STRONG_BULL"
    WEAK_BULL = "WEAK_BULL"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BEAR = "BEAR"
    PANIC = "PANIC"
    RECOVERY = "RECOVERY"


class StrategyLifecycle(StrEnum):
    CANDIDATE = "CANDIDATE"
    BACKTESTED = "BACKTESTED"
    PAPER_TESTED = "PAPER_TESTED"
    APPROVED = "APPROVED"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


class ExecutionConvention(StrEnum):
    SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN = "SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN"
