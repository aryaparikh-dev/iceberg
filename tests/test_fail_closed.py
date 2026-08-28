from iceberg.domain.models import TradeProposal

from tests.conftest import D, market_snapshot


def test_fail_closed_when_transaction_costs_unavailable(safe_context):
    class BrokenCostModel:
        def estimate(self, side, price, quantity):
            raise RuntimeError("cost service unavailable")

    safe_context.risk.cost_model = BrokenCostModel()
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="broken-costs")

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
    assert decision.rejection_reason == "TRANSACTION_COSTS_UNAVAILABLE"


def test_fail_closed_when_market_data_missing(safe_context):
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="no-data")

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=None,
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "MARKET_DATA_UNAVAILABLE"
