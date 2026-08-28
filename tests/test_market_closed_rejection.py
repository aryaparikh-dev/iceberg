from iceberg.domain.models import TradeProposal

from tests.conftest import D, ist_datetime, market_snapshot


def test_market_closed_rejection(safe_context):
    now = ist_datetime(16, 0)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="closed")

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "MARKET_CLOSED"
