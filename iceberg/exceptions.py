class IcebergError(Exception):
    """Base exception for the trading foundation."""


class FailClosedError(IcebergError):
    """Raised when a required safety precondition cannot be verified."""


class CapitalInvariantError(FailClosedError):
    """Raised when a capital invariant would be violated."""


class PermissionDeniedError(FailClosedError):
    """Raised when an actor lacks a required permission."""


class FundingError(FailClosedError):
    """Raised for invalid funding-ledger state changes."""


class LiveTradingDisabledError(FailClosedError):
    """Raised whenever live trading is requested in V1."""


class MarketClosedError(FailClosedError):
    """Raised when market state prevents trading."""


class ReconciliationError(FailClosedError):
    """Raised when broker, portfolio, or capital state cannot be reconciled."""


class DuplicateDecisionError(FailClosedError):
    """Raised when a decision or idempotency key has already been consumed."""
