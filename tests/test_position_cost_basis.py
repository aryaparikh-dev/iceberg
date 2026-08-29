from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker

from tests.conftest import D, TRADING_DATE, ist_datetime, market_snapshot


def decision(ctx, proposal, price):
    return ctx.risk.evaluate(
        proposal,
        portfolio=ctx.portfolio,
        capital=ctx.guard,
        market_data=market_snapshot(proposal.symbol, price, ctx.now),
        permissions=ctx.permissions,
        emergency_stop=ctx.emergency_stop,
        market_clock=ctx.clock,
        now=ctx.now,
    )


def test_price_decline_does_not_create_same_stock_allocation_loophole(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    first = TradeProposal.buy("ABC", price=D("10"), decision_id="basis-1")
    first_decision = decision(safe_context, first, D("10"))
    broker.submit_order(first, first_decision.authorization, "basis-1", safe_context.now)

    second = TradeProposal.buy("ABC", price=D("5"), decision_id="basis-2")
    second_decision = decision(safe_context, second, D("5"))

    assert not second_decision.approved
    assert second_decision.rejection_reason == "POSITION_LIMIT"
    assert safe_context.portfolio.gross_cost_basis("ABC") == D("10")


def test_remaining_permitted_allocation_uses_gross_cost_basis(safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    first = TradeProposal.buy("ABC", price=D("8"), decision_id="basis-8")
    broker.submit_order(first, decision(safe_context, first, D("8")).authorization, "basis-8", safe_context.now)

    second = TradeProposal.buy("ABC", price=D("2"), decision_id="basis-2", quantity=1)
    second_decision = decision(safe_context, second, D("2"))

    assert second_decision.approved
    assert second_decision.quantity == 1


def test_partial_sale_reduces_remaining_gross_cost_basis(settings, safe_context):
    from iceberg.capital.guard import CapitalGuard
    from iceberg.market.calendar import TradingCalendar
    from iceberg.market.clock import MarketClock
    from iceberg.portfolio.portfolio import Portfolio
    from iceberg.risk.engine import RiskEngine

    guard = CapitalGuard.initial(D("1000"), settings=settings)
    guard.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 0))
    portfolio = Portfolio()
    risk = RiskEngine(settings, safe_context.cost_model)
    clock = MarketClock(TradingCalendar(provider_verified=True), settings.market)
    broker = PaperBroker(portfolio, guard, safe_context.cost_model)
    buy = TradeProposal.buy("ABC", price=D("10"), decision_id="buy-ten", quantity=10)
    buy_decision = risk.evaluate(
        buy,
        portfolio=portfolio,
        capital=guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=clock,
        now=safe_context.now,
    )
    broker.submit_order(buy, buy_decision.authorization, "buy-ten", safe_context.now)

    sell = TradeProposal.sell("ABC", price=D("10"), decision_id="sell-four", quantity=4)
    sell_decision = risk.evaluate(
        sell,
        portfolio=portfolio,
        capital=guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=clock,
        now=safe_context.now,
    )
    broker.submit_order(sell, sell_decision.authorization, "sell-four", safe_context.now)

    assert portfolio.positions["ABC"].cost_basis == D("60")


def test_capital_growth_next_day_recalculates_stock_limit(safe_context):
    safe_context.guard.state.available_cash = D("200")
    safe_context.guard.state.settled_cash = D("200")
    safe_context.guard.state.broker_available_cash = D("200")
    safe_context.guard.settle_trading_day(safe_context.portfolio)
    safe_context.guard.create_daily_snapshot(ist_datetime(9, 0, day=6).date(), ist_datetime(9, 0, day=6))

    assert safe_context.guard.max_single_stock_value() == D("15.00")
