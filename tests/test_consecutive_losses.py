import pytest

from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker
from iceberg.exceptions import PermissionDeniedError
from iceberg.security.auth import ai_context

from tests.conftest import D, market_snapshot


def approved(ctx, proposal):
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


def round_trip(ctx, symbol, buy_price, sell_price, suffix):
    broker = PaperBroker(ctx.portfolio, ctx.guard, ctx.cost_model, settlement_lag_days=0)
    buy = TradeProposal.buy(symbol, price=D(buy_price), decision_id=f"buy-{suffix}")
    broker.submit_order(buy, approved(ctx, buy).authorization, f"buy-{suffix}", ctx.now)
    sell = TradeProposal.sell(symbol, price=D(sell_price), decision_id=f"sell-{suffix}", quantity=1)
    broker.submit_order(sell, approved(ctx, sell).authorization, f"sell-{suffix}", ctx.now)


def test_consecutive_losses_count_closed_trades(safe_context):
    round_trip(safe_context, "AAA", "10", "9", "a")
    round_trip(safe_context, "BBB", "10", "9", "b")

    assert safe_context.guard.state.consecutive_losses == 2


def test_consecutive_losses_persist_next_day(safe_context):
    safe_context.guard.state.consecutive_losses = 2
    safe_context.guard.create_daily_snapshot(safe_context.now.date().replace(day=6), safe_context.now.replace(day=6, hour=9, minute=0))

    assert safe_context.guard.state.consecutive_losses == 2


def test_win_resets_consecutive_losses(safe_context):
    safe_context.guard.state.consecutive_losses = 2
    round_trip(safe_context, "WIN", "10", "11", "win")

    assert safe_context.guard.state.consecutive_losses == 0


def test_break_even_trade_leaves_loss_count_unchanged(safe_context):
    safe_context.guard.state.consecutive_losses = 2
    round_trip(safe_context, "BE", "10", "10", "be")

    assert safe_context.guard.state.consecutive_losses == 2


def test_ai_cannot_reset_loss_counter(safe_context):
    safe_context.guard.state.consecutive_losses = 3

    with pytest.raises(PermissionDeniedError):
        safe_context.guard.reset_consecutive_losses(ai_context())
