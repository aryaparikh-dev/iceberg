from datetime import timedelta

from iceberg.domain.models import TradeProposal

from tests.conftest import D, market_snapshot


def test_risk_engine_rejects_single_stock_above_hard_cap(safe_context):
    proposal = TradeProposal.buy("ABC", price=D("11"), decision_id="stock-cap")

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "11", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "POSITION_LIMIT"


def test_risk_engine_rejects_daily_loss_limit(safe_context):
    safe_context.guard.state.total_equity = D("80")
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="loss-limit")

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
    assert decision.rejection_reason == "DAILY_LOSS_LIMIT"


def test_risk_engine_rejects_consecutive_loss_limit(safe_context):
    safe_context.guard.state.consecutive_losses = 3
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="consecutive-losses")

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
    assert decision.rejection_reason == "CONSECUTIVE_LOSS_LIMIT"


def test_risk_engine_rejects_stale_market_data(safe_context):
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="stale")
    old_data = market_snapshot("ABC", "10", safe_context.now - timedelta(minutes=10))

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=old_data,
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "STALE_MARKET_DATA"
