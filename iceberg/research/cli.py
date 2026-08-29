from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from iceberg.backtesting.engine import BacktestEngine
from iceberg.backtesting.market_data import SimulatedLiquidityAssumptionProfile
from iceberg.config.settings import default_settings
from iceberg.data.loaders import HistoricalDataLoader
from iceberg.data.metadata import metadata_for_file
from iceberg.data.models import AdjustmentMode, CorporateActionStatus
from iceberg.data.sources import CSVHistoricalDataSource
from iceberg.data.storage import LocalMarketDataRepository
from iceberg.data.validation import DataQualityRules, HistoricalDataQualityValidator
from iceberg.market.calendar import StaticBacktestCalendar
from iceberg.market.clock import MarketClock
from iceberg.research.experiments import ExperimentRunner
from iceberg.research.walk_forward import WalkForwardSplitter
from iceberg.risk.costs import FixedTransactionCostModel
from iceberg.risk.slippage import FixedBpsSlippageModel
from iceberg.strategies.baseline import BreakoutStrategy, MeanReversionStrategy, MomentumStrategy, TrendFollowingStrategy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m iceberg.research", description="Research-only Indian equity backtesting tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-data")
    _add_data_args(validate)

    normalize = subparsers.add_parser("normalize-data")
    _add_data_args(normalize)
    normalize.add_argument("--output-root", default="data")
    normalize.add_argument("--output-name", required=True)

    backtest = subparsers.add_parser("backtest")
    _add_data_args(backtest)
    backtest.add_argument("--strategy", choices=sorted(_STRATEGIES), default="momentum")
    backtest.add_argument("--initial-capital", default="100")
    backtest.add_argument("--assume-liquidity", action="store_true")

    compare = subparsers.add_parser("compare")
    _add_data_args(compare)
    compare.add_argument("--strategies", default="momentum,trend_following,mean_reversion,breakout")
    compare.add_argument("--initial-capital", default="100")
    compare.add_argument("--assume-liquidity", action="store_true")

    walk = subparsers.add_parser("walk-forward")
    walk.add_argument("--start", required=True)
    walk.add_argument("--end", required=True)
    walk.add_argument("--train-days", type=int, required=True)
    walk.add_argument("--validation-days", type=int, required=True)
    walk.add_argument("--test-days", type=int, required=True)
    walk.add_argument("--step-days", type=int, required=True)
    walk.add_argument("--mode", choices=("rolling", "expanding"), default="rolling")

    args = parser.parse_args(argv)
    if args.command == "validate-data":
        dataset = _load_dataset(args, reject_failures=False)
        print(json.dumps(dataset.quality_report.to_dict(), indent=2, sort_keys=True))
        return 1 if dataset.quality_report.failed else 0
    if args.command == "normalize-data":
        dataset = _load_dataset(args, reject_failures=True)
        paths = LocalMarketDataRepository(args.output_root).write_normalized_dataset(dataset, args.output_name)
        print(json.dumps({"bars": str(paths[0]), "metadata": str(paths[1]), "quality": str(paths[2])}, indent=2, sort_keys=True))
        return 0
    if args.command == "backtest":
        dataset = _load_dataset(args, reject_failures=True)
        report = _run_backtest(dataset.candles_by_symbol(), args.strategy, args.initial_capital, args.assume_liquidity)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "compare":
        dataset = _load_dataset(args, reject_failures=True)
        reports = _compare(dataset.candles_by_symbol(), args.strategies.split(","), args.initial_capital, args.assume_liquidity)
        print(json.dumps({name: report.to_dict() for name, report in reports.items()}, indent=2, sort_keys=True))
        return 0
    if args.command == "walk-forward":
        splits = _walk_forward(args)
        print(json.dumps([_split_to_dict(split) for split in splits], indent=2, sort_keys=True))
        return 0
    return 2


def _add_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--csv", required=True, help="Local CSV file containing legally obtained or synthetic OHLCV data.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--source-id", default="local-csv")
    parser.add_argument("--allow-irregular-spacing", action="store_true")


def _load_dataset(args, *, reject_failures: bool):
    source = CSVHistoricalDataSource(args.csv, source_id=args.source_id, interval=args.interval)
    settings = default_settings()
    bars = source.get_candles([args.symbol])
    calendar = StaticBacktestCalendar(trading_days={bar.trading_date for bar in bars})
    rules = DataQualityRules(require_regular_spacing=not args.allow_irregular_spacing)
    validator = HistoricalDataQualityValidator(market_clock=MarketClock(calendar, settings.market), calendar=calendar, rules=rules)
    metadata = metadata_for_file(
        args.csv,
        source="local-csv",
        source_identifier=args.source_id,
        symbol=args.symbol,
        exchange="NSE",
        interval=args.interval,
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_methodology="raw input; no corporate-action adjustment applied",
        corporate_action_status=CorporateActionStatus.UNKNOWN,
    )
    return HistoricalDataLoader(source, validator).load_symbol(args.symbol, metadata, reject_failures=reject_failures)


def _run_backtest(candles_by_symbol, strategy_name: str, initial_capital: str, assume_liquidity: bool):
    settings = default_settings()
    settings.capital.initial_capital_inr = Decimal(initial_capital)
    all_dates = {candle.timestamp.date() for candles in candles_by_symbol.values() for candle in candles}
    return BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(schedule_version="explicit-fixed-research-cli"),
        slippage_model=FixedBpsSlippageModel(Decimal("0")),
        calendar=StaticBacktestCalendar(trading_days=all_dates),
        liquidity_assumption_profile=_liquidity_profile() if assume_liquidity else None,
    ).run(candles_by_symbol, _strategy(strategy_name))


def _compare(candles_by_symbol, strategy_names: list[str], initial_capital: str, assume_liquidity: bool):
    settings = default_settings()
    settings.capital.initial_capital_inr = Decimal(initial_capital)
    all_dates = {candle.timestamp.date() for candles in candles_by_symbol.values() for candle in candles}

    def engine_factory():
        return BacktestEngine(
            settings=settings,
            cost_model=FixedTransactionCostModel(schedule_version="explicit-fixed-research-cli"),
            slippage_model=FixedBpsSlippageModel(Decimal("0")),
            calendar=StaticBacktestCalendar(trading_days=all_dates),
            liquidity_assumption_profile=_liquidity_profile() if assume_liquidity else None,
        )

    return ExperimentRunner(engine_factory).compare(candles_by_symbol, [_strategy(name.strip()) for name in strategy_names if name.strip()])


def _walk_forward(args):
    splitter = WalkForwardSplitter()
    kwargs = {
        "start": date.fromisoformat(args.start),
        "end": date.fromisoformat(args.end),
        "train_days": args.train_days,
        "validation_days": args.validation_days,
        "test_days": args.test_days,
        "step_days": args.step_days,
    }
    if args.mode == "rolling":
        return splitter.rolling(**kwargs)
    return splitter.expanding(
        start=kwargs["start"],
        end=kwargs["end"],
        initial_train_days=kwargs["train_days"],
        validation_days=kwargs["validation_days"],
        test_days=kwargs["test_days"],
        step_days=kwargs["step_days"],
    )


def _split_to_dict(split) -> dict:
    return {
        "train": {"start": split.train.start.isoformat(), "end": split.train.end.isoformat()},
        "validation": {"start": split.validation.start.isoformat(), "end": split.validation.end.isoformat()},
        "test": {"start": split.test.start.isoformat(), "end": split.test.end.isoformat()},
        "shuffled": split.shuffled,
    }


def _liquidity_profile():
    return SimulatedLiquidityAssumptionProfile(
        average_volume=Decimal("100000"),
        average_traded_value=Decimal("10000000"),
        bid_ask_spread_fraction=Decimal("0.001"),
        estimated_price_impact_fraction=Decimal("0.001"),
        name="explicit-cli-assumption",
    )


_STRATEGIES = {
    "momentum": MomentumStrategy,
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "breakout": BreakoutStrategy,
}


def _strategy(name: str):
    try:
        return _STRATEGIES[name]()
    except KeyError as exc:
        raise SystemExit(f"unknown strategy {name}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
