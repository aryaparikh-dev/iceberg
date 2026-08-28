import pytest

from iceberg.exceptions import CapitalInvariantError, FailClosedError

from tests.conftest import D


def test_capital_guard_tracks_cash_equity_and_deployed_capital(safe_context):
    safe_context.guard.apply_buy("ABC", quantity=1, execution_price=D("10"), transaction_costs=D("0.50"))

    state = safe_context.guard.state
    assert state.available_cash == D("89.50")
    assert state.deployed_capital == D("10")
    assert state.market_value == D("10")
    assert state.total_equity == D("99.50")
    assert state.available_cash >= 0


def test_capital_guard_rejects_unknown_broker_cash(safe_context):
    safe_context.guard.mark_broker_state_unknown()

    with pytest.raises(FailClosedError):
        safe_context.guard.spendable_cash()


def test_capital_guard_never_applies_negative_cash(safe_context):
    with pytest.raises(CapitalInvariantError):
        safe_context.guard.apply_buy("ABC", quantity=1, execution_price=D("101"), transaction_costs=D("0"))
