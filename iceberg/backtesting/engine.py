from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from statistics import mean, pstdev

from iceberg.ai.regime import RegimeDetector
from iceberg.backtesting.market_data import BacktestMarketDataAdapter, SimulatedLiquidityAssumptionProfile
from iceberg.capital.guard import CapitalGuard
from iceberg.capital.manager import CapitalManager
from iceberg.config.settings import Settings, default_settings
from iceberg.data.validation import DataValidator
from iceberg.domain.enums import ExecutionConvention, TradeSide
from iceberg.domain.models import Candle, TradeProposal, money
from iceberg.exceptions import ConfigurationError, ReconciliationError
from iceberg.execution.brokers import PaperBroker
from iceberg.execution.engine import ExecutionEngine
from iceberg.execution.exit_manager import ExitManager
from iceberg.logging.audit import InMemoryAuditLogger
from iceberg.market.calendar import TradingCalendar, UnknownTradingCalendar
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import TransactionCostModel
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.engine import RiskEngine
from iceberg.risk.permissions import PermissionManager
from iceberg.risk.slippage import SlippageModel
from iceberg.research.results import DailyEquityPoint, TradeLedgerEntry
from iceberg.strategies.base import Strategy


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"{type(value)!r} is not JSON serializable")


@dataclass
class BacktestReport:
    starting_capital: Decimal
    ending_capital: Decimal
    net_profit: Decimal
    return_percentage: Decimal
    trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    average_win: Decimal
    average_loss: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal | None
    maximum_drawdown: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None
    transaction_costs: Decimal
    slippage: Decimal
    user_distributions: Decimal
    final_ai_capital: Decimal
    rejected_trades: int
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    metric_unavailable_reasons: dict[str, str] = field(default_factory=dict)
    execution_convention: ExecutionConvention = ExecutionConvention.SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN
    liquidity_assumptions_used: bool = False
    experiment_id: str | None = None
    strategy_name: str = "unknown"
    strategy_version: str = "unversioned"
    parameter_set: dict = field(default_factory=dict)
    universe: str = "unspecified"
    symbols_tested: tuple[str, ...] = field(default_factory=tuple)
    date_range: tuple[date | None, date | None] = (None, None)
    bar_interval: str = "unknown"
    initial_ai_capital: Decimal = money("0")
    ending_ai_capital: Decimal = money("0")
    gross_profit: Decimal = money("0")
    largest_win: Decimal | None = None
    largest_loss: Decimal | None = None
    capital_utilization: Decimal | None = None
    average_holding_time_seconds: Decimal | None = None
    exposure_time_fraction: Decimal | None = None
    turnover: Decimal | None = None
    liquidity_assumption_details: dict = field(default_factory=dict)
    transaction_cost_schedule_used: str = "unspecified"
    transaction_cost_schedule_verified: bool = False
    adjustment_mode: str = "RAW"
    survivorship_bias_risk: bool = True
    data_quality_status: str = "NOT_SUPPLIED"
    benchmark_results: dict = field(default_factory=dict)
    trade_ledger: tuple[TradeLedgerEntry, ...] = field(default_factory=tuple)
    daily_equity_curve: tuple[DailyEquityPoint, ...] = field(default_factory=tuple)
    regime_analysis: dict = field(default_factory=dict)
    attribution: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=_json_default, sort_keys=True))


class BacktestEngine:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        cost_model: TransactionCostModel | None = None,
        slippage_model: SlippageModel | None = None,
        calendar: TradingCalendar | None = None,
        liquidity_assumption_profile: SimulatedLiquidityAssumptionProfile | None = None,
        execution_convention: ExecutionConvention = ExecutionConvention.SIGNAL_ON_BAR_CLOSE_EXECUTE_NEXT_BAR_OPEN,
        store=None,
    ) -> None:
        self.settings = settings or default_settings()
        if cost_model is None:
            raise ConfigurationError("backtests require an explicit transaction cost model")
        if slippage_model is None:
            raise ConfigurationError("backtests require an explicit slippage model")
        self.cost_model = cost_model
        self.slippage_model = slippage_model
        self.calendar = calendar or UnknownTradingCalendar()
        self.market_data_adapter = BacktestMarketDataAdapter(liquidity_assumption_profile)
        self.execution_convention = execution_convention
        self.store = store

    def run(self, candles_by_symbol: dict[str, list[Candle]], strategy: Strategy) -> BacktestReport:
        capital = CapitalGuard.initial(self.settings.capital.initial_capital_inr, settings=self.settings, store=self.store)
        portfolio = Portfolio()
        if self.store is not None:
            portfolio.persist(self.store)
        permissions = PermissionManager.default_ai()
        emergency_stop = EmergencyStop(active=False, store=self.store)
        clock = MarketClock(self.calendar, self.settings.market)
        risk = RiskEngine(self.settings, self.cost_model)
        audit = InMemoryAuditLogger(store=self.store)
        broker = PaperBroker(
            portfolio,
            capital,
            self.cost_model,
            slippage_model=self.slippage_model,
            settlement_lag_days=0,
            store=self.store,
        )
        engine = ExecutionEngine(broker, audit, emergency_stop, permissions)
        exits = ExitManager(clock)
        regime_detector = RegimeDetector()
        validator = DataValidator(self.settings.data.max_market_data_age)
        manager = CapitalManager(capital, None, self.settings, self.calendar)

        timeline = self._timeline(candles_by_symbol)
        histories: dict[str, list[Candle]] = {symbol.upper(): [] for symbol in candles_by_symbol}
        pending: list[TradeProposal] = []
        latest_prices: dict[str, Decimal] = {}
        equity_curve = [capital.state.total_equity]
        daily_equity_curve: list[DailyEquityPoint] = []
        current_day: date | None = None
        current_day_starting_capital: Decimal | None = None
        peak_daily_capital = capital.state.total_equity

        for now, symbol, candle in timeline:
            if current_day != now.date():
                if current_day is not None:
                    settlement = self._finish_day(capital, portfolio, broker, current_day)
                    point = self._daily_equity_point(
                        current_day,
                        current_day_starting_capital or capital.state.daily_starting_capital,
                        settlement.user_distribution,
                        capital,
                        audit,
                        peak_daily_capital,
                    )
                    daily_equity_curve.append(point)
                    peak_daily_capital = max(peak_daily_capital, point.ending_ai_capital)
                manager.start_trading_day(now.date(), now.replace(hour=9, minute=0, second=0, microsecond=0))
                current_day = now.date()
                current_day_starting_capital = capital.state.daily_starting_capital

            pending = self._execute_pending(pending, candle, engine, risk, portfolio, capital, clock, now)

            histories[symbol].append(candle)
            validator.validate_candles(histories[symbol], expected_symbol=symbol, now=now)
            latest_prices[symbol] = candle.close

            regime = regime_detector.detect(histories[symbol])
            for proposal in strategy.generate(symbol, tuple(histories[symbol]), now, regime):
                if proposal.side is not TradeSide.HOLD:
                    pending.append(proposal)
                else:
                    audit.log(proposal, risk.reject("HOLD_NO_EXECUTION", proposal), timestamp=now)

            if clock.is_force_exit_window(now):
                self._force_exit_on_candle(
                    symbol,
                    candle.close,
                    candle.volume,
                    now,
                    portfolio,
                    capital,
                    engine,
                    risk,
                    exits,
                    clock,
                )

            self._mark_to_market_or_fail_closed(portfolio, capital, latest_prices)
            equity_curve.append(capital.state.total_equity)

        if current_day is not None:
            settlement = self._finish_day(capital, portfolio, broker, current_day)
            point = self._daily_equity_point(
                current_day,
                current_day_starting_capital or capital.state.daily_starting_capital,
                settlement.user_distribution,
                capital,
                audit,
                peak_daily_capital,
            )
            daily_equity_curve.append(point)
            equity_curve.append(capital.state.total_equity)

        start_date = min((row[0].date() for row in timeline), default=None)
        end_date = max((row[0].date() for row in timeline), default=None)
        return self._report(
            capital,
            audit,
            equity_curve,
            strategy=strategy,
            symbols_tested=tuple(sorted(candles_by_symbol)),
            date_range=(start_date, end_date),
            daily_equity_curve=tuple(daily_equity_curve),
        )

    def _execute_pending(
        self,
        pending: list[TradeProposal],
        candle: Candle,
        engine: ExecutionEngine,
        risk: RiskEngine,
        portfolio: Portfolio,
        capital: CapitalGuard,
        clock: MarketClock,
        now: datetime,
    ) -> list[TradeProposal]:
        remaining: list[TradeProposal] = []
        for proposal in pending:
            if proposal.symbol != candle.symbol:
                remaining.append(proposal)
                continue
            executable = self._next_bar_open_proposal(proposal, candle.open, now)
            engine.submit_proposal(
                executable,
                risk_engine=risk,
                portfolio=portfolio,
                capital=capital,
                market_data=self.market_data_adapter.snapshot(
                    executable.symbol,
                    executable.proposed_price,
                    now,
                    observed_volume=candle.volume,
                ),
                market_clock=clock,
                now=now,
                idempotency_key=executable.decision_id,
            )
        return remaining

    def _next_bar_open_proposal(self, proposal: TradeProposal, open_price: Decimal, now: datetime) -> TradeProposal:
        return TradeProposal(
            decision_id=proposal.decision_id,
            symbol=proposal.symbol,
            side=proposal.side,
            proposed_price=open_price,
            strategy=proposal.strategy,
            quantity=proposal.quantity,
            timestamp=now,
            signal_type=proposal.signal_type,
            asset_class=proposal.asset_class,
            confidence=proposal.confidence,
            market_regime=proposal.market_regime,
            key_signals=proposal.key_signals,
            relevant_features=proposal.relevant_features,
            stop_or_invalidation_level=proposal.stop_or_invalidation_level,
            summary="Executed by next-bar-open convention",
        )

    def _finish_day(
        self,
        capital: CapitalGuard,
        portfolio: Portfolio,
        broker: PaperBroker,
        trading_day: date,
    ):
        if not broker.reconcile():
            capital.mark_portfolio_uncertain()
            raise ReconciliationError("backtest reconciliation failed")
        if not portfolio.is_flat():
            capital.mark_portfolio_uncertain()
            raise ReconciliationError(f"missing force-exit-window market data for {trading_day.isoformat()}")
        if not broker.reconcile():
            capital.mark_portfolio_uncertain()
            raise ReconciliationError("backtest reconciliation failed before settlement")
        return capital.settle_trading_day(portfolio)

    def _force_exit_on_candle(
        self,
        symbol: str,
        price: Decimal,
        volume: Decimal,
        now: datetime,
        portfolio: Portfolio,
        capital: CapitalGuard,
        engine: ExecutionEngine,
        risk: RiskEngine,
        exits: ExitManager,
        clock: MarketClock,
    ) -> None:
        proposals = exits.create_force_exit_proposals(portfolio, {symbol: price}, now)
        for proposal in proposals:
            result = engine.submit_proposal(
                proposal,
                risk_engine=risk,
                portfolio=portfolio,
                capital=capital,
                market_data=self.market_data_adapter.snapshot(
                    proposal.symbol,
                    proposal.proposed_price,
                    now,
                    observed_volume=volume,
                ),
                market_clock=clock,
                now=now,
                idempotency_key=proposal.decision_id,
            )
            if result.execution is None or result.execution.status == "REJECTED":
                capital.mark_portfolio_uncertain()
                raise ReconciliationError("forced exit failed closed")

    def _mark_to_market_or_fail_closed(self, portfolio: Portfolio, capital: CapitalGuard, latest_prices: dict[str, Decimal]) -> None:
        missing = [symbol for symbol in portfolio.positions if symbol not in latest_prices]
        if missing:
            capital.mark_portfolio_uncertain()
            raise ReconciliationError(f"missing price for open position: {missing[0]}")
        capital.update_mark_to_market(portfolio.total_market_value(latest_prices))

    def _timeline(self, candles_by_symbol: dict[str, list[Candle]]) -> list[tuple[datetime, str, Candle]]:
        rows: list[tuple[datetime, str, Candle]] = []
        for symbol, candles in candles_by_symbol.items():
            for candle in sorted(candles, key=lambda c: c.timestamp):
                rows.append((candle.timestamp, symbol.upper(), candle))
        return sorted(rows, key=lambda row: (row[0], row[1]))

    def _report(
        self,
        capital: CapitalGuard,
        audit: InMemoryAuditLogger,
        equity_curve: list[Decimal],
        *,
        strategy: Strategy | None = None,
        symbols_tested: tuple[str, ...] = tuple(),
        date_range: tuple[date | None, date | None] = (None, None),
        daily_equity_curve: tuple[DailyEquityPoint, ...] = tuple(),
    ) -> BacktestReport:
        execution_records = [record for record in audit.records if record.order_id and record.rejection_reason is None]
        exits = [record for record in execution_records if record.decision == TradeSide.SELL.value]
        pnl_values = [record.net_pnl for record in exits]
        wins = [pnl for pnl in pnl_values if pnl > 0]
        losses = [pnl for pnl in pnl_values if pnl < 0]
        rejected: dict[str, int] = {}
        total_costs = money("0")
        slippage = money("0")
        gross_profit = money("0")
        for record in audit.records:
            if record.rejection_reason:
                rejected[record.rejection_reason] = rejected.get(record.rejection_reason, 0) + 1
            total_costs += record.transaction_costs
            slippage += abs(record.slippage)
            gross_profit += record.gross_pnl
        starting = capital.state.starting_capital
        ending = capital.state.total_equity
        net_profit = ending - starting
        metric_reasons: dict[str, str] = {}
        profit_factor = None
        if losses:
            profit_factor = sum(wins, Decimal("0")) / abs(sum(losses, Decimal("0"))) if wins else Decimal("0")
        elif wins:
            metric_reasons["profit_factor"] = "no losing closed trades"
        else:
            metric_reasons["profit_factor"] = "no closed trades"
        sharpe, sortino = self._risk_adjusted_metrics(equity_curve, metric_reasons)
        expectancy = None if not pnl_values else sum(pnl_values, Decimal("0")) / Decimal(len(pnl_values))
        if expectancy is None:
            metric_reasons["expectancy"] = "no closed trades"
        trade_ledger = self._trade_ledger(audit.records, starting)
        largest_win = max(wins) if wins else None
        largest_loss = min(losses) if losses else None
        if trade_ledger:
            holding = [entry.holding_duration_seconds for entry in trade_ledger if entry.holding_duration_seconds is not None]
            average_holding = None if not holding else Decimal(sum(holding)) / Decimal(len(holding))
        else:
            average_holding = None
            metric_reasons["average_holding_time_seconds"] = "no completed trades"
        turnover = None if starting == 0 else sum((record.gross_pnl + abs(record.net_pnl) for record in exits), Decimal("0")) / starting
        utilization = None if starting == 0 else max((point.starting_capital for point in daily_equity_curve), default=starting) / starting
        cost_schedule, cost_verified = self._cost_schedule_metadata()
        regime_analysis = self._regime_analysis(exits)
        attribution = self._attribution(exits)
        return BacktestReport(
            starting_capital=starting,
            ending_capital=ending,
            net_profit=net_profit,
            return_percentage=money("0") if starting == 0 else net_profit / starting,
            trades=len(execution_records),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=money("0") if not pnl_values else Decimal(len(wins)) / Decimal(len(pnl_values)),
            average_win=money("0") if not wins else sum(wins, Decimal("0")) / Decimal(len(wins)),
            average_loss=money("0") if not losses else sum(losses, Decimal("0")) / Decimal(len(losses)),
            profit_factor=profit_factor,
            expectancy=expectancy,
            maximum_drawdown=self._max_drawdown(equity_curve),
            sharpe=sharpe,
            sortino=sortino,
            transaction_costs=total_costs,
            slippage=slippage,
            user_distributions=capital.state.user_distribution,
            final_ai_capital=capital.state.next_day_capital,
            rejected_trades=sum(rejected.values()),
            rejection_reasons=rejected,
            metric_unavailable_reasons=metric_reasons,
            execution_convention=self.execution_convention,
            liquidity_assumptions_used=self.market_data_adapter.uses_simulated_liquidity,
            strategy_name=getattr(strategy, "name", "unknown"),
            strategy_version=getattr(strategy, "version", "unversioned"),
            parameter_set=getattr(strategy, "parameters", {}),
            symbols_tested=symbols_tested,
            date_range=date_range,
            initial_ai_capital=starting,
            ending_ai_capital=capital.state.next_day_capital,
            gross_profit=gross_profit,
            largest_win=largest_win,
            largest_loss=largest_loss,
            capital_utilization=utilization,
            average_holding_time_seconds=average_holding,
            exposure_time_fraction=None,
            turnover=turnover,
            liquidity_assumption_details=self._liquidity_assumption_details(),
            transaction_cost_schedule_used=cost_schedule,
            transaction_cost_schedule_verified=cost_verified,
            trade_ledger=trade_ledger,
            daily_equity_curve=daily_equity_curve,
            regime_analysis=regime_analysis,
            attribution=attribution,
        )

    def _daily_equity_point(
        self,
        trading_day: date,
        starting_capital: Decimal,
        distribution: Decimal,
        capital: CapitalGuard,
        audit: InMemoryAuditLogger,
        peak_daily_capital: Decimal,
    ) -> DailyEquityPoint:
        records = [record for record in audit.records if record.timestamp is not None and record.timestamp.date() == trading_day]
        gross = sum((record.gross_pnl for record in records), Decimal("0"))
        costs = sum((record.transaction_costs for record in records), Decimal("0"))
        slippage = sum((abs(record.slippage) for record in records), Decimal("0"))
        net = sum((record.net_pnl for record in records), Decimal("0"))
        ending = capital.state.next_day_capital
        peak = max(peak_daily_capital, ending)
        drawdown = money("0") if peak == 0 else (peak - ending) / peak
        return DailyEquityPoint(trading_day, starting_capital, gross, costs, slippage, net, distribution, ending, drawdown)

    def _trade_ledger(self, records, starting_capital: Decimal) -> tuple[TradeLedgerEntry, ...]:
        open_entries: dict[str, list] = {}
        ledger: list[TradeLedgerEntry] = []
        for record in records:
            if not record.order_id or record.rejection_reason or record.execution_price is None:
                continue
            if record.decision == TradeSide.BUY.value:
                open_entries.setdefault(record.symbol, []).append(record)
                continue
            if record.decision != TradeSide.SELL.value:
                continue
            if not open_entries.get(record.symbol):
                continue
            entry = open_entries[record.symbol].pop(0)
            entry_value = entry.execution_price * record.quantity if entry.execution_price is not None else money("0")
            duration = None
            if entry.timestamp is not None and record.timestamp is not None:
                duration = int((record.timestamp - entry.timestamp).total_seconds())
            return_pct = None if entry_value == 0 else record.net_pnl / entry_value
            allocation = None if starting_capital == 0 else entry_value / starting_capital
            ledger.append(
                TradeLedgerEntry(
                    trade_id=f"TRADE-{len(ledger) + 1}",
                    decision_id=record.decision_id,
                    symbol=record.symbol,
                    strategy=entry.strategy,
                    entry_signal_timestamp=entry.timestamp,
                    entry_execution_timestamp=entry.timestamp,
                    entry_price=entry.execution_price,
                    quantity=record.quantity,
                    entry_costs=entry.transaction_costs,
                    exit_signal_timestamp=record.timestamp,
                    exit_execution_timestamp=record.timestamp,
                    exit_price=record.execution_price,
                    exit_costs=record.transaction_costs,
                    gross_pnl=record.gross_pnl,
                    net_pnl=record.net_pnl,
                    return_percentage=return_pct,
                    holding_duration_seconds=duration,
                    exit_reason="FORCED_EXIT" if record.strategy == "ExitManager" else "STRATEGY_EXIT",
                    market_regime=record.market_regime,
                    slippage=entry.slippage + record.slippage,
                    capital_at_entry=starting_capital,
                    position_allocation_percentage=allocation,
                )
            )
        return tuple(ledger)

    def _cost_schedule_metadata(self) -> tuple[str, bool]:
        charges = getattr(self.cost_model, "charges", None)
        if charges is not None and hasattr(charges, "metadata"):
            metadata = charges.metadata()
            return str(metadata["schedule_version"]), bool(metadata["verified"])
        return getattr(self.cost_model, "schedule_version", self.cost_model.__class__.__name__), False

    def _liquidity_assumption_details(self) -> dict:
        profile = self.market_data_adapter.liquidity_assumptions
        if profile is None:
            return {"used": False}
        return {
            "used": True,
            "name": profile.name,
            "average_volume": str(profile.average_volume),
            "average_traded_value": str(profile.average_traded_value),
            "bid_ask_spread_fraction": str(profile.bid_ask_spread_fraction),
            "estimated_price_impact_fraction": str(profile.estimated_price_impact_fraction),
        }

    def _regime_analysis(self, exits) -> dict:
        result: dict[str, dict] = {}
        for record in exits:
            regime = record.market_regime or "UNKNOWN"
            item = result.setdefault(regime, {"trades": 0, "wins": 0, "net_pnl": money("0")})
            item["trades"] += 1
            item["wins"] += int(record.net_pnl > 0)
            item["net_pnl"] += record.net_pnl
        for item in result.values():
            item["win_rate"] = money("0") if item["trades"] == 0 else Decimal(item["wins"]) / Decimal(item["trades"])
        return result

    def _attribution(self, exits) -> dict:
        attribution = {"symbol": {}, "month": {}, "year": {}, "strategy": {}, "regime": {}}
        for record in exits:
            keys = {
                "symbol": record.symbol,
                "month": record.timestamp.strftime("%Y-%m") if record.timestamp else "UNKNOWN",
                "year": record.timestamp.strftime("%Y") if record.timestamp else "UNKNOWN",
                "strategy": record.strategy,
                "regime": record.market_regime or "UNKNOWN",
            }
            for bucket, key in keys.items():
                item = attribution[bucket].setdefault(key, {"trades": 0, "net_pnl": money("0")})
                item["trades"] += 1
                item["net_pnl"] += record.net_pnl
        return attribution

    def _max_drawdown(self, equity_curve: list[Decimal]) -> Decimal:
        peak = equity_curve[0] if equity_curve else money("0")
        max_dd = money("0")
        for point in equity_curve:
            peak = max(peak, point)
            if peak:
                max_dd = max(max_dd, (peak - point) / peak)
        return max_dd

    def _risk_adjusted_metrics(self, equity_curve: list[Decimal], reasons: dict[str, str]) -> tuple[Decimal | None, Decimal | None]:
        if len(equity_curve) < 3:
            reasons["sharpe"] = "insufficient equity observations"
            reasons["sortino"] = "insufficient equity observations"
            return None, None
        returns = []
        for previous, current in zip(equity_curve, equity_curve[1:]):
            if previous:
                returns.append(float((current - previous) / previous))
        if len(returns) < 2 or pstdev(returns) == 0:
            reasons["sharpe"] = "zero or insufficient return variance"
            sharpe = None
        else:
            sharpe = Decimal(str(mean(returns) / pstdev(returns)))
        downside = [value for value in returns if value < 0]
        if len(downside) < 2 or pstdev(downside) == 0:
            reasons["sortino"] = "zero or insufficient downside variance"
            sortino = None
        else:
            sortino = Decimal(str(mean(returns) / pstdev(downside)))
        return sharpe, sortino
