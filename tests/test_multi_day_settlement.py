from iceberg.capital.manager import CapitalManager
from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker

from tests.conftest import D, ist_datetime, market_snapshot


def approve(ctx, proposal, now):
    return ctx.risk.evaluate(
        proposal,
        portfolio=ctx.portfolio,
        capital=ctx.guard,
        market_data=market_snapshot(proposal.symbol, proposal.proposed_price, now),
        permissions=ctx.permissions,
        emergency_stop=ctx.emergency_stop,
        market_clock=ctx.clock,
        now=now,
    )


def test_multi_day_snapshot_uses_prior_next_day_capital(safe_context):
    safe_context.guard.state.available_cash = D("111")
    safe_context.guard.state.settled_cash = D("111")
    safe_context.guard.state.broker_available_cash = D("111")
    safe_context.guard.settle_trading_day(safe_context.portfolio)
    manager = CapitalManager(
        capital=safe_context.guard,
        funding_ledger=None,
        settings=safe_context.settings,
        calendar=safe_context.calendar,
    )

    manager.start_trading_day(ist_datetime(9, 0, day=6).date(), ist_datetime(9, 0, day=6))

    assert safe_context.guard.state.daily_starting_capital == D("105.50")
    assert safe_context.guard.state.available_cash == D("105.50")


def test_multi_day_accounting_does_not_double_count_prior_realized_pnl(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model, settlement_lag_days=0)
    buy_day_1 = TradeProposal.buy("ABC", price=D("10"), decision_id="day1-buy", quantity=1)
    sell_day_1 = TradeProposal.sell("ABC", price=D("111"), decision_id="day1-sell", quantity=1)

    broker.submit_order(buy_day_1, approve(safe_context, buy_day_1, ist_datetime(10, 0)).authorization, "day1-buy", ist_datetime(10, 0))
    broker.submit_order(sell_day_1, approve(safe_context, sell_day_1, ist_datetime(10, 1)).authorization, "day1-sell", ist_datetime(10, 1))
    settlement_day_1 = safe_context.guard.settle_trading_day(safe_context.portfolio)

    assert settlement_day_1.user_distribution == D("50.50")
    assert safe_context.guard.state.next_day_capital == D("150.50")
    assert safe_context.guard.state.realized_pnl == D("0")

    manager = CapitalManager(safe_context.guard, None, safe_context.settings, safe_context.calendar)
    manager.start_trading_day(ist_datetime(9, 0, day=6).date(), ist_datetime(9, 0, day=6))

    assert safe_context.guard.state.daily_starting_capital == D("150.50")
    assert safe_context.guard.state.realized_pnl == D("0")
    assert safe_context.guard.state.unrealized_pnl == D("0")

    buy_day_2 = TradeProposal.buy("ABC", price=D("10"), decision_id="day2-buy", quantity=1)
    sell_day_2 = TradeProposal.sell("ABC", price=D("20"), decision_id="day2-sell", quantity=1)
    broker.submit_order(buy_day_2, approve(safe_context, buy_day_2, ist_datetime(10, 0, day=6)).authorization, "day2-buy", ist_datetime(10, 0, day=6))
    broker.submit_order(sell_day_2, approve(safe_context, sell_day_2, ist_datetime(10, 1, day=6)).authorization, "day2-sell", ist_datetime(10, 1, day=6))

    assert safe_context.guard.state.available_cash == D("160.50")
    assert safe_context.guard.state.realized_pnl == D("10")

    settlement_day_2 = safe_context.guard.settle_trading_day(safe_context.portfolio)

    assert settlement_day_2.user_distribution == D("0")
    assert safe_context.guard.state.user_distribution == D("50.50")
    assert safe_context.guard.state.next_day_capital == D("160.50")
    assert safe_context.guard.state.realized_pnl == D("0")
