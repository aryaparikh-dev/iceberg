from datetime import timedelta
from decimal import Decimal

import pytest

from iceberg.domain.enums import TradeSide
from iceberg.domain.models import RiskDecision, TradeProposal
from iceberg.execution.authorization import ExecutionAuthorization
from iceberg.execution.brokers import PaperBroker

from tests.conftest import D, ist_datetime, market_snapshot


def approved_decision(ctx, proposal):
    return ctx.risk.evaluate(
        proposal,
        portfolio=ctx.portfolio,
        capital=ctx.guard,
        market_data=market_snapshot(proposal.symbol, proposal.proposed_price, ctx.now),
        permissions=ctx.permissions,
        emergency_stop=ctx.emergency_stop,
        market_clock=ctx.clock,
        now=ctx.now,
    )


def test_fake_risk_decision_cannot_execute(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="fake")
    fake = RiskDecision(True, "fake", "ABC", TradeSide.BUY, quantity=1)

    execution = broker.submit_order(proposal, fake, idempotency_key="fake-key", now=safe_context.now)

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "RISK_AUTHORIZATION_REQUIRED"
    assert safe_context.portfolio.is_flat()


def test_execution_authorization_cannot_be_constructed_by_strategy(safe_context):
    with pytest.raises(Exception):
        ExecutionAuthorization(
            decision_id="x",
            symbol="ABC",
            side=TradeSide.BUY,
            quantity=1,
            approved_price=Decimal("10"),
            estimated_costs=Decimal("0"),
            capital_required=Decimal("10"),
            approved_at=safe_context.now,
            charge_schedule_version="fake",
        )


def test_authorization_bound_to_decision(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="auth-a")
    decision = approved_decision(safe_context, proposal)
    different = TradeProposal.buy("ABC", price=D("10"), decision_id="auth-b")

    execution = broker.submit_order(different, decision.authorization, idempotency_key="bad-decision", now=safe_context.now)

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "AUTHORIZATION_MISMATCH"


def test_authorization_bound_to_quantity(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="auth-qty")
    decision = approved_decision(safe_context, proposal)
    larger = TradeProposal.buy("ABC", price=D("10"), decision_id="auth-qty", quantity=2)

    execution = broker.submit_order(larger, decision.authorization, idempotency_key="bad-qty", now=safe_context.now)

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "AUTHORIZATION_MISMATCH"


def test_authorization_single_use(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="single-use")
    decision = approved_decision(safe_context, proposal)

    first = broker.submit_order(proposal, decision.authorization, idempotency_key="single-a", now=safe_context.now)
    second = broker.submit_order(proposal, decision.authorization, idempotency_key="single-b", now=safe_context.now)

    assert first.status == "FILLED"
    assert second.status == "REJECTED"
    assert second.rejection_reason == "DUPLICATE_DECISION"


def test_strategy_cannot_call_broker_directly_without_authorization(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="direct")

    execution = broker.submit_order(proposal, None, idempotency_key="direct-key", now=safe_context.now)

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "RISK_AUTHORIZATION_REQUIRED"


def test_execution_authorization_expires_before_late_submission(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="expired-auth")
    decision = approved_decision(safe_context, proposal)
    late = safe_context.now + timedelta(seconds=safe_context.settings.risk.execution_authorization_validity_seconds + 1)

    execution = broker.submit_order(proposal, decision.authorization, idempotency_key="expired-auth", now=late)

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "AUTHORIZATION_EXPIRED"
    assert safe_context.portfolio.is_flat()


def test_execution_authorization_cannot_cross_trading_session(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="next-day-auth")
    decision = approved_decision(safe_context, proposal)

    execution = broker.submit_order(proposal, decision.authorization, idempotency_key="next-day-auth", now=ist_datetime(10, 0, day=6))

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "AUTHORIZATION_SESSION_MISMATCH"
    assert safe_context.portfolio.is_flat()
