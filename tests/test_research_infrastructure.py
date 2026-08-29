from datetime import date
from decimal import Decimal

import pytest

from iceberg.backtesting.engine import BacktestEngine
from iceberg.backtesting.market_data import SimulatedLiquidityAssumptionProfile
from iceberg.data.universe import StaticUniverse
from iceberg.domain.models import Candle, TradeProposal
from iceberg.market.calendar import StaticBacktestCalendar
from iceberg.research.benchmarks import BuyAndHoldBenchmark, CashBenchmark
from iceberg.research.diagnostics import OverfittingDiagnosticEngine
from iceberg.research.experiments import ExperimentConfig, ExperimentRunner, config_from_selection
from iceberg.research.optimization import GridSearch, RandomSearch
from iceberg.research.results import export_daily_equity_json, export_trade_ledger_csv, export_trade_ledger_json
from iceberg.research.walk_forward import TimeRange, TrainValidationTestSplit, WalkForwardSplitter
from iceberg.risk.costs import FixedTransactionCostModel
from iceberg.risk.slippage import FixedBpsSlippageModel
from iceberg.strategies.base import Strategy

from tests.conftest import D, ist_datetime


class BuyFirstBarStrategy(Strategy):
    name = "buy_first_research"
    version = "1.0"
    parameters = {"buy_once": True}

    def __init__(self):
        self.sent = False

    def generate(self, symbol, history, now, regime):
        if not self.sent:
            self.sent = True
            return [TradeProposal.buy(symbol, price=history[-1].close, decision_id=f"research-buy-{symbol}", quantity=1, timestamp=now, strategy=self.name)]
        return []


def profile():
    return SimulatedLiquidityAssumptionProfile(
        average_volume=D("100000"),
        average_traded_value=D("10000000"),
        bid_ask_spread_fraction=D("0.001"),
        estimated_price_impact_fraction=D("0.001"),
    )


def candles(symbol="ABC"):
    return [
        Candle(symbol, ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle(symbol, ist_datetime(10, 1), D("20"), D("20"), D("20"), D("20"), D("1000")),
        Candle(symbol, ist_datetime(15, 20), D("30"), D("30"), D("30"), D("30"), D("1000")),
    ]


def engine(settings):
    settings.capital.initial_capital_inr = D("1000")
    return BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(schedule_version="fixed-research-costs"),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
        liquidity_assumption_profile=profile(),
    )


def run_report(settings):
    return engine(settings).run({"ABC": candles()}, BuyFirstBarStrategy())


def test_backtest_report_contains_trade_ledger_daily_equity_and_serializes(settings):
    report = run_report(settings)
    serialized = report.to_dict()

    assert report.strategy_name == "buy_first_research"
    assert report.strategy_version == "1.0"
    assert report.transaction_cost_schedule_used == "fixed-research-costs"
    assert report.adjustment_mode == "RAW"
    assert report.survivorship_bias_risk is True
    assert len(report.trade_ledger) == 1
    assert report.trade_ledger[0].symbol == "ABC"
    assert report.trade_ledger[0].gross_pnl == D("10")
    assert len(report.daily_equity_curve) == 1
    assert report.daily_equity_curve[0].trading_date == date(2026, 1, 5)
    assert serialized["trade_ledger"][0]["exit_reason"] == "FORCED_EXIT"


def test_trade_ledger_and_equity_curve_export_csv_and_json(settings, tmp_path):
    report = run_report(settings)
    csv_path = tmp_path / "ledger.csv"
    json_path = tmp_path / "ledger.json"
    equity_path = tmp_path / "equity.json"

    export_trade_ledger_csv(report.trade_ledger, csv_path)
    export_trade_ledger_json(report.trade_ledger, json_path)
    export_daily_equity_json(report.daily_equity_curve, equity_path)

    assert "trade_id" in csv_path.read_text()
    assert "TRADE-1" in json_path.read_text()
    assert "ending_ai_capital" in equity_path.read_text()


def test_buy_and_hold_and_cash_benchmarks_are_separate_from_strategy_trades():
    benchmark = BuyAndHoldBenchmark("ABC-buy-hold").evaluate(candles())
    cash = CashBenchmark().evaluate(start_date=date(2026, 1, 5), end_date=date(2026, 1, 5))

    assert benchmark.total_return == D("2")
    assert benchmark.maximum_drawdown == D("0")
    assert cash.total_return == D("0")


def test_walk_forward_splits_are_chronological_and_never_shuffled():
    splitter = WalkForwardSplitter()
    split = splitter.train_validation_test(
        TimeRange(date(2019, 1, 1), date(2022, 12, 31)),
        TimeRange(date(2023, 1, 1), date(2023, 12, 31)),
        TimeRange(date(2024, 1, 1), date(2024, 12, 31)),
    )

    assert split.shuffled is False
    with pytest.raises(ValueError):
        TrainValidationTestSplit(split.train, split.validation, split.test, shuffled=True)
    assert WalkForwardSplitter().rolling(
        start=date(2020, 1, 1),
        end=date(2020, 1, 30),
        train_days=10,
        validation_days=5,
        test_days=5,
        step_days=5,
    )


def test_grid_search_records_every_attempt_and_uses_train_period_only():
    train_range = TimeRange(date(2020, 1, 1), date(2020, 12, 31))
    seen_ranges = []

    def evaluator(params, supplied_range):
        seen_ranges.append(supplied_range)
        return {"return": Decimal(params["lookback"]) / Decimal("10"), "trades": params["lookback"], "maximum_drawdown": D("0.1"), "duration_days": 365}

    result = GridSearch({"lookback": [1, 3, 5]}).run(
        evaluator,
        train_range=train_range,
        objective="return",
        constraints={"minimum_trades": 3, "maximum_drawdown": D("0.2")},
    )

    assert len(result.attempts) == 3
    assert result.best_parameters == {"lookback": 5}
    assert result.train_only is True
    assert seen_ranges == [train_range, train_range, train_range]


def test_random_search_is_seed_reproducible():
    first = RandomSearch({"lookback": [2, 4, 8]}, attempts=5, seed=7).candidates()
    second = RandomSearch({"lookback": [2, 4, 8]}, attempts=5, seed=7).candidates()

    assert first == second


def test_overfitting_diagnostics_flags_obvious_research_mistakes():
    diagnostics = OverfittingDiagnosticEngine().evaluate(
        total_trades=5,
        train_return=D("0.80"),
        test_return=D("-0.10"),
        parameter_attempts=100,
        symbols={"ABC": 5},
        period_returns=[D("0.9"), D("-0.2")],
    )

    assert diagnostics.has_warnings
    assert "VERY_FEW_TRADES" in diagnostics.warnings
    assert "TRAIN_TEST_PERFORMANCE_GAP" in diagnostics.warnings
    assert "ONE_STOCK_DEPENDENCE" in diagnostics.warnings


def test_experiment_manifest_is_reproducible_and_records_inputs():
    config = ExperimentConfig(
        strategy_name="momentum",
        strategy_version="1.0",
        parameters={"lookback": 3},
        universe="manual",
        symbols=("ABC",),
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
        bar_interval="1m",
        initial_capital=D("1000"),
        transaction_cost_schedule="fixed-research-costs",
        slippage_model="FixedBpsSlippageModel(0)",
        adjustment_mode="RAW",
        data_checksums={"ABC": "abc123"},
        random_seed=42,
        code_commit_sha="deadbeef",
    )

    assert config.reproducible_id() == config.reproducible_id()
    manifest = config.manifest()
    assert manifest["data_checksums"] == {"ABC": "abc123"}
    assert manifest["experiment_id"] == config.reproducible_id()


def test_experiment_config_can_be_built_from_universe_selection():
    selection = StaticUniverse("manual", ["ABC"]).eligible_symbols(date(2026, 1, 5))

    config = config_from_selection(
        strategy=BuyFirstBarStrategy(),
        selection=selection,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
        bar_interval="1m",
        initial_capital=D("1000"),
        transaction_cost_schedule="fixed",
        slippage_model="fixed-bps-0",
        adjustment_mode="RAW",
    )

    assert config.universe == "manual"
    assert config.symbols == ("ABC",)


def test_experiment_runner_compares_multiple_strategies_on_same_dataset(settings):
    def engine_factory():
        return engine(settings)

    runner = ExperimentRunner(engine_factory)
    results = runner.compare({"ABC": candles()}, [BuyFirstBarStrategy(), BuyFirstBarStrategy()])

    assert list(results) == ["buy_first_research"]
    assert results["buy_first_research"].trades == 2


def test_multi_symbol_timeline_ordering_is_deterministic(settings):
    timeline = engine(settings)._timeline(
        {
            "XYZ": [Candle("XYZ", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000"))],
            "ABC": [Candle("ABC", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000"))],
        }
    )

    assert [symbol for _, symbol, _ in timeline] == ["ABC", "XYZ"]
