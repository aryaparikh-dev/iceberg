from iceberg.capital.guard import CapitalGuard
from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker
from iceberg.persistence.repositories import SQLiteStateStore
from iceberg.portfolio.portfolio import Portfolio

from tests.conftest import D, market_snapshot


def approved(ctx, proposal, portfolio, capital):
    return ctx.risk.evaluate(
        proposal,
        portfolio=portfolio,
        capital=capital,
        market_data=market_snapshot(proposal.symbol, proposal.proposed_price, ctx.now),
        permissions=ctx.permissions,
        emergency_stop=ctx.emergency_stop,
        market_clock=ctx.clock,
        now=ctx.now,
    )


def test_restart_restores_positions(tmp_path, safe_context):
    store = SQLiteStateStore(tmp_path / "state.sqlite3")
    capital = CapitalGuard.initial(D("100"), settings=safe_context.settings, store=store)
    capital.create_daily_snapshot(safe_context.guard.state.current_trading_date, safe_context.guard.state.snapshot_created_at)
    portfolio = Portfolio()
    broker = PaperBroker(portfolio, capital, safe_context.cost_model, store=store)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="persist-pos")
    broker.submit_order(proposal, approved(safe_context, proposal, portfolio, capital).authorization, "persist-pos", safe_context.now)

    restored = Portfolio.load(store)

    assert restored.positions["ABC"].quantity == 1
    assert restored.positions["ABC"].cost_basis == D("10")


def test_restart_restores_cash(tmp_path, safe_context):
    store = SQLiteStateStore(tmp_path / "cash.sqlite3")
    capital = CapitalGuard.initial(D("100"), settings=safe_context.settings, store=store)
    portfolio = Portfolio()
    broker = PaperBroker(portfolio, capital, safe_context.cost_model, store=store)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="persist-cash")
    broker.submit_order(proposal, approved(safe_context, proposal, portfolio, capital).authorization, "persist-cash", safe_context.now)

    restored = CapitalGuard.load(store, settings=safe_context.settings)

    assert restored.state.available_cash == D("90")


def test_restart_restores_idempotency(tmp_path, safe_context):
    store = SQLiteStateStore(tmp_path / "idem.sqlite3")
    capital = CapitalGuard.initial(D("100"), settings=safe_context.settings, store=store)
    portfolio = Portfolio()
    broker = PaperBroker(portfolio, capital, safe_context.cost_model, store=store)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="idem")
    first = broker.submit_order(proposal, approved(safe_context, proposal, portfolio, capital).authorization, "idem-key", safe_context.now)

    restored_broker = PaperBroker(Portfolio.load(store), CapitalGuard.load(store, safe_context.settings), safe_context.cost_model, store=store)
    replay = restored_broker.submit_order(proposal, None, "idem-key", safe_context.now)

    assert replay.order_id == first.order_id


def test_restart_prevents_duplicate_execution(tmp_path, safe_context):
    store = SQLiteStateStore(tmp_path / "dup.sqlite3")
    capital = CapitalGuard.initial(D("100"), settings=safe_context.settings, store=store)
    portfolio = Portfolio()
    broker = PaperBroker(portfolio, capital, safe_context.cost_model, store=store)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="dup-persist")
    broker.submit_order(proposal, approved(safe_context, proposal, portfolio, capital).authorization, "dup-a", safe_context.now)

    restored_portfolio = Portfolio.load(store)
    restored_capital = CapitalGuard.load(store, safe_context.settings)
    restored_broker = PaperBroker(restored_portfolio, restored_capital, safe_context.cost_model, store=store)
    new_decision = approved(safe_context, proposal, restored_portfolio, restored_capital)
    execution = restored_broker.submit_order(proposal, new_decision.authorization, "dup-b", safe_context.now)

    assert execution.status == "REJECTED"
    assert execution.rejection_reason == "DUPLICATE_DECISION"


def test_reconciliation_mismatch_fails_closed(tmp_path, safe_context):
    store = SQLiteStateStore(tmp_path / "mismatch.sqlite3")
    capital = CapitalGuard.initial(D("100"), settings=safe_context.settings, store=store)
    portfolio = Portfolio()
    portfolio.record_buy("ABC", 1, D("10"))
    broker = PaperBroker(portfolio, capital, safe_context.cost_model, store=store)

    assert not broker.reconcile()
    assert capital.state.portfolio_state == "UNCERTAIN"
