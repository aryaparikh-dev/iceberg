from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker

from tests.conftest import D, market_snapshot


def test_no_leverage_rejects_order_above_cash(safe_context):
    safe_context.guard.state.available_cash = D("5")
    safe_context.guard.state.broker_available_cash = D("5")
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="no-leverage")

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


def test_paper_broker_cannot_create_negative_cash_from_unapproved_order(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="rejected")
    decision = safe_context.risk.reject("INSUFFICIENT_CASH", proposal)

    execution = broker.submit_order(proposal, decision.authorization, idempotency_key="reject-key", now=safe_context.now)

    assert execution.status == "REJECTED"
    assert safe_context.guard.state.available_cash == D("100")
