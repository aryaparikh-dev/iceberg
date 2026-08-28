from iceberg.domain.models import TradeProposal

from tests.conftest import D, ist_datetime, market_snapshot


def test_last_entry_cutoff_blocks_new_positions_but_not_exits(safe_context):
    now = ist_datetime(15, 11)
    buy = TradeProposal.buy("ABC", price=D("10"), decision_id="late-buy")

    buy_decision = safe_context.risk.evaluate(
        buy,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=now,
    )

    safe_context.portfolio.record_buy("ABC", 1, D("10"))
    sell = TradeProposal.sell("ABC", price=D("10"), decision_id="late-sell", quantity=1)
    sell_decision = safe_context.risk.evaluate(
        sell,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=now,
    )

    assert not buy_decision.approved
    assert buy_decision.rejection_reason == "LAST_ENTRY_CUTOFF"
    assert sell_decision.approved
