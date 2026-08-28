from decimal import Decimal

import pytest

from iceberg.capital.guard import CapitalGuard
from iceberg.domain.models import TradeProposal
from iceberg.risk.costs import FixedTransactionCostModel

from tests.conftest import D, TRADING_DATE, ist_datetime, market_snapshot


@pytest.mark.parametrize(
    ("capital", "price", "expected_quantity"),
    [
        ("100", "10", 1),
        ("100", "11", 0),
        ("1000", "100", 1),
        ("1000", "101", 0),
        ("10000", "1000", 1),
        ("10000", "1001", 0),
    ],
)
def test_position_sizing_obeys_ten_percent_stock_cap(settings, capital, price, expected_quantity):
    guard = CapitalGuard.initial(Decimal(capital), settings=settings)
    guard.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 0))

    assert guard.max_whole_shares_for_price(Decimal(price)) == expected_quantity


def test_transaction_cost_boundary_rejects_when_cash_would_go_negative(safe_context):
    safe_context.guard.state.available_cash = D("10")
    safe_context.guard.state.broker_available_cash = D("10")
    safe_context.guard.state.settled_cash = D("10")
    safe_context.risk.cost_model = FixedTransactionCostModel(buy_cost=D("0.01"))
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="cost-boundary")

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "INSUFFICIENT_CASH"
