from iceberg.capital.guard import CapitalGuard
from iceberg.config.settings import default_settings
from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker
from iceberg.market.calendar import TradingCalendar
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import FixedTransactionCostModel
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.engine import RiskEngine
from iceberg.risk.permissions import PermissionManager
from iceberg.risk.slippage import FixedBpsSlippageModel

from tests.conftest import D, TRADING_DATE, ist_datetime, market_snapshot


def approve(proposal, portfolio, capital, settings, now):
    return RiskEngine(settings=settings, cost_model=FixedTransactionCostModel()).evaluate(
        proposal,
        portfolio=portfolio,
        capital=capital,
        market_data=market_snapshot(proposal.symbol, proposal.proposed_price, now),
        permissions=PermissionManager.default_ai(),
        emergency_stop=EmergencyStop(active=False),
        market_clock=MarketClock(TradingCalendar(provider_verified=True), settings.market),
        now=now,
    )


def test_slippage_cannot_breach_stock_cap():
    settings = default_settings()
    capital = CapitalGuard.initial(D("100"), settings=settings)
    capital.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 0))
    portfolio = Portfolio()
    broker = PaperBroker(
        portfolio,
        capital,
        FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("100")),
    )
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="slip-stock", quantity=1)
    decision = approve(proposal, portfolio, capital, settings, ist_datetime(10, 0))

    execution = broker.submit_order(proposal, decision.authorization, "slip-stock", ist_datetime(10, 0))

    assert decision.approved
    assert execution.status == "REJECTED"
    assert "stock allocation" in execution.rejection_reason
    assert portfolio.is_flat()
    assert capital.state.available_cash == D("100")
    assert capital.state.deployed_capital == D("0")


def test_slippage_cannot_breach_portfolio_cap():
    settings = default_settings()
    settings.capital.initial_capital_inr = D("1000")
    settings.risk.maximum_positions = 11
    capital = CapitalGuard.initial(D("1000"), settings=settings)
    capital.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 0))
    portfolio = Portfolio()
    for idx in range(9):
        portfolio.record_buy(f"SEED{idx}", 1, D("100"))
    portfolio.record_buy("SEED9", 1, D("90"))
    capital.state.deployed_capital = D("990")
    capital.state.market_value = D("990")
    capital.state.available_cash = D("10")
    capital.state.broker_available_cash = D("10")
    capital.state.settled_cash = D("10")
    capital.state.total_equity = D("1000")
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="slip-portfolio", quantity=1)
    decision = approve(proposal, portfolio, capital, settings, ist_datetime(10, 0))
    broker = PaperBroker(
        portfolio,
        capital,
        FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("100")),
    )

    execution = broker.submit_order(proposal, decision.authorization, "slip-portfolio", ist_datetime(10, 0))

    assert decision.approved
    assert execution.status == "REJECTED"
    assert "portfolio allocation" in execution.rejection_reason
    assert "ABC" not in portfolio.positions
    assert capital.state.available_cash == D("10")
    assert capital.state.deployed_capital == D("990")


def test_slippage_cannot_breach_available_cash():
    settings = default_settings()
    settings.capital.initial_capital_inr = D("1000")
    settings.risk.daily_loss_limit_fraction = D("2")
    capital = CapitalGuard.initial(D("1000"), settings=settings)
    capital.create_daily_snapshot(TRADING_DATE, ist_datetime(9, 0))
    capital.state.available_cash = D("10")
    capital.state.broker_available_cash = D("10")
    capital.state.settled_cash = D("10")
    capital.state.total_equity = D("10")
    portfolio = Portfolio()
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="slip-cash", quantity=1)
    decision = approve(proposal, portfolio, capital, settings, ist_datetime(10, 0))
    broker = PaperBroker(
        portfolio,
        capital,
        FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("100")),
    )

    execution = broker.submit_order(proposal, decision.authorization, "slip-cash", ist_datetime(10, 0))

    assert decision.approved
    assert execution.status == "REJECTED"
    assert "spendable cash" in execution.rejection_reason
    assert portfolio.is_flat()
    assert capital.state.available_cash == D("10")
