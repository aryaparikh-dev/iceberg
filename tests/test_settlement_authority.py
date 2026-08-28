import pytest

from iceberg.exceptions import ReconciliationError

from tests.conftest import D


def test_settlement_cannot_supply_fake_equity(safe_context):
    with pytest.raises(TypeError):
        safe_context.guard.settle_trading_day(D("999999"), positions_flat=True)


def test_settlement_requires_flat_portfolio(safe_context):
    safe_context.portfolio.record_buy("ABC", 1, D("10"))

    with pytest.raises(ReconciliationError):
        safe_context.guard.settle_trading_day(safe_context.portfolio)


def test_settlement_requires_reconciliation(safe_context):
    safe_context.guard.mark_broker_state_unknown()

    with pytest.raises(ReconciliationError):
        safe_context.guard.settle_trading_day(safe_context.portfolio)


def test_settlement_uses_authoritative_cash(safe_context):
    safe_context.guard.state.available_cash = D("111")
    safe_context.guard.state.settled_cash = D("111")
    safe_context.guard.state.broker_available_cash = D("111")

    settlement = safe_context.guard.settle_trading_day(safe_context.portfolio)

    assert settlement.user_distribution == D("5.50")
    assert safe_context.guard.state.next_day_capital == D("105.50")
