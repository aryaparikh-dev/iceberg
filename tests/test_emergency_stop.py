from iceberg.domain.models import TradeProposal
from iceberg.risk.emergency import EmergencyStop

from tests.conftest import D, market_snapshot


def test_emergency_stop_blocks_new_orders(safe_context):
    emergency = EmergencyStop(active=True)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="halted")

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=emergency,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "EMERGENCY_STOP"


def test_emergency_stop_allows_controlled_exits(safe_context):
    safe_context.portfolio.record_buy("ABC", 1, D("10"))
    emergency = EmergencyStop(active=True, allow_position_exits=True)
    proposal = TradeProposal.sell("ABC", price=D("10"), decision_id="exit", quantity=1)

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=emergency,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert decision.approved
