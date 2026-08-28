from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker

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


def test_buy_rolls_back_if_portfolio_update_fails(monkeypatch, safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="atomic-buy")
    decision = approved(safe_context, proposal)
    starting_cash = safe_context.guard.state.available_cash

    def fail_buy(*args, **kwargs):
        raise RuntimeError("portfolio failed")

    monkeypatch.setattr(safe_context.portfolio, "record_buy", fail_buy)
    execution = broker.submit_order(proposal, decision.authorization, "atomic-buy", safe_context.now)

    assert execution.status == "REJECTED"
    assert safe_context.guard.state.available_cash == starting_cash
    assert safe_context.portfolio.positions == {}


def test_sell_rolls_back_if_capital_update_fails(monkeypatch, safe_context):
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model)
    buy = TradeProposal.buy("ABC", price=D("10"), decision_id="atomic-seed")
    broker.submit_order(buy, approved(safe_context, buy).authorization, "atomic-seed", safe_context.now)
    sell = TradeProposal.sell("ABC", price=D("10"), decision_id="atomic-sell", quantity=1)
    sell_decision = approved(safe_context, sell)

    def fail_sell(*args, **kwargs):
        raise RuntimeError("capital failed")

    monkeypatch.setattr(safe_context.guard, "apply_sell", fail_sell)
    execution = broker.submit_order(sell, sell_decision.authorization, "atomic-sell", safe_context.now)

    assert execution.status == "REJECTED"
    assert safe_context.portfolio.positions["ABC"].quantity == 1
    assert safe_context.guard.state.available_cash == D("90")


def test_execution_transaction_is_atomic(monkeypatch, tmp_path, safe_context):
    from iceberg.persistence.repositories import SQLiteStateStore

    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    safe_context.guard.store = store
    safe_context.guard.persist()
    broker = PaperBroker(safe_context.portfolio, safe_context.guard, safe_context.cost_model, store=store)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="atomic-db")
    decision = approved(safe_context, proposal)

    def fail_positions(*args, **kwargs):
        raise RuntimeError("db position write failed")

    monkeypatch.setattr(store, "save_positions", fail_positions)
    execution = broker.submit_order(proposal, decision.authorization, "atomic-db", safe_context.now)

    assert execution.status == "REJECTED"
    assert store.load_capital_state().available_cash == D("100")
    assert store.load_positions() == {}
