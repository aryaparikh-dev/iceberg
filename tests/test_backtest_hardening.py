import pytest

from iceberg.backtesting.engine import BacktestEngine
from iceberg.backtesting.market_data import SimulatedLiquidityAssumptionProfile
from iceberg.domain.enums import TradeSide
from iceberg.domain.models import Candle, TradeProposal
from iceberg.exceptions import ConfigurationError, ReconciliationError
from iceberg.market.calendar import StaticBacktestCalendar
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import FixedTransactionCostModel
from iceberg.risk.slippage import FixedBpsSlippageModel
from iceberg.strategies.base import Strategy

from tests.conftest import D, ist_datetime


class BuyFirstBarStrategy(Strategy):
    name = "buy_first"

    def __init__(self):
        self.sent = False

    def generate(self, symbol, history, now, regime):
        if not self.sent:
            self.sent = True
            return [TradeProposal.buy(symbol, price=history[-1].close, decision_id="bt-buy", quantity=1, timestamp=now, strategy=self.name)]
        return []


def profile():
    return SimulatedLiquidityAssumptionProfile(
        average_volume=D("100000"),
        average_traded_value=D("10000000"),
        bid_ask_spread_fraction=D("0.001"),
        estimated_price_impact_fraction=D("0.001"),
    )


def candles():
    return [
        Candle("ABC", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle("ABC", ist_datetime(10, 1), D("20"), D("20"), D("20"), D("20"), D("1000")),
        Candle("ABC", ist_datetime(15, 20), D("20"), D("20"), D("20"), D("20"), D("1000")),
    ]


def profit_candles():
    return [
        Candle("ABC", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle("ABC", ist_datetime(10, 1), D("10"), D("111"), D("10"), D("111"), D("1000")),
        Candle("ABC", ist_datetime(15, 20), D("111"), D("111"), D("111"), D("111"), D("1000")),
    ]


def no_exit_window_candles():
    return [
        Candle("ABC", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle("ABC", ist_datetime(10, 1), D("10"), D("10"), D("10"), D("10"), D("1000")),
    ]


def pre_exit_window_candles():
    return [
        Candle("ABC", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle("ABC", ist_datetime(10, 1), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle("ABC", ist_datetime(15, 19), D("10"), D("10"), D("10"), D("10"), D("1000")),
    ]


def test_backtest_requires_transaction_cost_schedule_and_slippage(settings):
    with pytest.raises(ConfigurationError):
        BacktestEngine(settings=settings, slippage_model=FixedBpsSlippageModel(D("0")), calendar=StaticBacktestCalendar())


def test_backtest_no_longer_fabricates_liquidity(settings):
    report = BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
    ).run({"ABC": candles()}, BuyFirstBarStrategy())

    assert report.trades == 0
    assert report.rejection_reasons["LIQUIDITY_REJECTED"] == 1
    assert report.liquidity_assumptions_used is False


def test_no_same_bar_lookahead_executes_next_bar_open(settings, tmp_path):
    from iceberg.persistence.repositories import SQLiteStateStore

    settings.capital.initial_capital_inr = D("1000")
    store = SQLiteStateStore(tmp_path / "bt.sqlite3")
    report = BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
        liquidity_assumption_profile=profile(),
        store=store,
    ).run({"ABC": candles()}, BuyFirstBarStrategy())

    executions = [execution for execution in store.load_executions() if execution.status == "FILLED"]
    assert executions[0].execution_price == D("20")
    assert report.execution_convention.value == "SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN"


def test_multi_symbol_mark_to_market_uses_latest_price_for_each_symbol(settings):
    from iceberg.capital.guard import CapitalGuard

    engine = BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(),
    )
    capital = CapitalGuard.initial(D("1000"), settings=settings)
    portfolio = Portfolio()
    portfolio.record_buy("ABC", 1, D("10"))
    portfolio.record_buy("XYZ", 2, D("10"))

    engine._mark_to_market_or_fail_closed(portfolio, capital, {"ABC": D("15"), "XYZ": D("7")})

    assert capital.state.market_value == D("29")


def test_missing_price_for_open_position_fails_closed(settings):
    from iceberg.capital.guard import CapitalGuard

    engine = BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(),
    )
    capital = CapitalGuard.initial(D("1000"), settings=settings)
    portfolio = Portfolio()
    portfolio.record_buy("ABC", 1, D("10"))

    with pytest.raises(ReconciliationError):
        engine._mark_to_market_or_fail_closed(portfolio, capital, {})

    assert capital.state.portfolio_state == "UNCERTAIN"


def test_daily_backtest_settlement_and_forced_exit_distribution(settings, tmp_path):
    from iceberg.persistence.repositories import SQLiteStateStore

    store = SQLiteStateStore(tmp_path / "daily.sqlite3")
    report = BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
        liquidity_assumption_profile=profile(),
        store=store,
    ).run({"ABC": profit_candles()}, BuyFirstBarStrategy())

    assert report.trades == 2
    assert report.user_distributions == D("50.50")
    assert report.final_ai_capital == D("150.50")


def test_charge_schedule_version_recorded_in_execution(settings, tmp_path):
    from iceberg.persistence.repositories import SQLiteStateStore

    settings.capital.initial_capital_inr = D("1000")
    store = SQLiteStateStore(tmp_path / "charges.sqlite3")
    BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(schedule_version="unit-cost-schedule"),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
        liquidity_assumption_profile=profile(),
        store=store,
    ).run({"ABC": candles()}, BuyFirstBarStrategy())

    filled = [execution for execution in store.load_executions() if execution.status == "FILLED"]
    assert filled[0].charge_schedule_version == "unit-cost-schedule"


def test_stale_midday_price_cannot_be_used_for_force_exit(settings, tmp_path):
    from iceberg.capital.guard import CapitalGuard
    from iceberg.persistence.repositories import SQLiteStateStore

    store = SQLiteStateStore(tmp_path / "stale-exit.sqlite3")
    with pytest.raises(ReconciliationError):
        BacktestEngine(
            settings=settings,
            cost_model=FixedTransactionCostModel(),
            slippage_model=FixedBpsSlippageModel(D("0")),
            calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
            liquidity_assumption_profile=profile(),
            store=store,
        ).run({"ABC": no_exit_window_candles()}, BuyFirstBarStrategy())

    executions = store.load_executions()
    assert [execution.side for execution in executions if execution.status == "FILLED"] == [TradeSide.BUY]
    assert CapitalGuard.load(store, settings=settings).state.portfolio_state == "UNCERTAIN"


def test_force_exit_requires_exit_window_market_data(settings, tmp_path):
    from iceberg.persistence.repositories import SQLiteStateStore

    store = SQLiteStateStore(tmp_path / "pre-window-exit.sqlite3")
    with pytest.raises(ReconciliationError, match="force-exit-window"):
        BacktestEngine(
            settings=settings,
            cost_model=FixedTransactionCostModel(),
            slippage_model=FixedBpsSlippageModel(D("0")),
            calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
            liquidity_assumption_profile=profile(),
            store=store,
        ).run({"ABC": pre_exit_window_candles()}, BuyFirstBarStrategy())


def test_missing_exit_price_prevents_daily_settlement(settings, tmp_path):
    from iceberg.capital.guard import CapitalGuard
    from iceberg.persistence.repositories import SQLiteStateStore

    store = SQLiteStateStore(tmp_path / "missing-exit-price.sqlite3")
    with pytest.raises(ReconciliationError):
        BacktestEngine(
            settings=settings,
            cost_model=FixedTransactionCostModel(),
            slippage_model=FixedBpsSlippageModel(D("0")),
            calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
            liquidity_assumption_profile=profile(),
            store=store,
        ).run(
            {
                "ABC": no_exit_window_candles(),
                "XYZ": [Candle("XYZ", ist_datetime(15, 20), D("50"), D("50"), D("50"), D("50"), D("1000"))],
            },
            BuyFirstBarStrategy(),
        )

    capital = CapitalGuard.load(store, settings=settings)
    assert capital.state.portfolio_state == "UNCERTAIN"
    assert capital.state.next_day_capital == settings.capital.initial_capital_inr
