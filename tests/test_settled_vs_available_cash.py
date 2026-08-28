from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker

from tests.conftest import D, market_snapshot


def test_sale_proceeds_are_accounted_separately_from_settled_broker_cash(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model, settlement_lag_days=1)
    safe_context.guard.apply_buy("ABC", 1, D("10"), D("0"))
    safe_context.portfolio.record_buy("ABC", 1, D("10"))

    sell = TradeProposal.sell("ABC", price=D("10"), decision_id="sell", quantity=1)
    decision = safe_context.risk.evaluate(
        sell,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    broker.submit_order(sell, decision, idempotency_key="sell-key", now=safe_context.now)

    assert safe_context.guard.state.available_cash == D("100")
    assert safe_context.guard.state.unsettled_cash == D("10")
    assert safe_context.guard.state.broker_available_cash == D("90")
    assert safe_context.guard.spendable_cash() == D("90")


def test_unsettled_cash_cannot_fund_new_entries(safe_context):
    safe_context.guard.state.available_cash = D("100")
    safe_context.guard.state.broker_available_cash = D("9")
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="uses-unsettled")

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
