from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker

from tests.conftest import D, market_snapshot


def test_duplicate_decision_or_idempotency_key_does_not_create_two_positions(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="dup")
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

    first = broker.submit_order(proposal, decision, idempotency_key="same-key", now=safe_context.now)
    second = broker.submit_order(proposal, decision, idempotency_key="same-key", now=safe_context.now)
    third = broker.submit_order(proposal, decision, idempotency_key="different-key", now=safe_context.now)

    assert first.order_id == second.order_id
    assert third.status == "REJECTED"
    assert third.rejection_reason == "DUPLICATE_DECISION"
    assert safe_context.portfolio.positions["ABC"].quantity == 1
