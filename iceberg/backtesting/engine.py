from __future__ import annotations

from dataclasses import dataclass, field
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
from iceberg.strategies.base import Strategy


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
        current_day: date | None = None

        for now, symbol, candle in timeline:
            if current_day != now.date():
                if current_day is not None:
                    self._finish_day(capital, portfolio, broker, engine, risk, exits, latest_prices, current_day, now)
                manager.start_trading_day(now.date(), now.replace(hour=9, minute=0, second=0, microsecond=0))
                current_day = now.date()

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

            forced = exits.create_force_exit_proposals(portfolio, latest_prices, now)
            for proposal in forced:
                result = engine.submit_proposal(
                    proposal,
                    risk_engine=risk,
                    portfolio=portfolio,
                    capital=capital,
                    market_data=self.market_data_adapter.snapshot(proposal.symbol, proposal.proposed_price, now),
                    market_clock=clock,
                    now=now,
                    idempotency_key=proposal.decision_id,
                )
                if result.execution is None or result.execution.status == "REJECTED":
                    capital.mark_portfolio_uncertain()

            self._mark_to_market_or_fail_closed(portfolio, capital, latest_prices)
            equity_curve.append(capital.state.total_equity)

        if current_day is not None:
            self._finish_day(capital, portfolio, broker, engine, risk, exits, latest_prices, current_day, timeline[-1][0])
            equity_curve.append(capital.state.total_equity)

        return self._report(capital, audit, equity_curve)

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
                market_data=self.market_data_adapter.snapshot(executable.symbol, executable.proposed_price, now),
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
        engine: ExecutionEngine,
        risk: RiskEngine,
        exits: ExitManager,
        latest_prices: dict[str, Decimal],
        trading_day: date,
        now: datetime,
    ) -> None:
        if not broker.reconcile():
            capital.mark_portfolio_uncertain()
            raise ReconciliationError("backtest reconciliation failed")
        if not portfolio.is_flat():
            force_time = now.replace(
                year=trading_day.year,
                month=trading_day.month,
                day=trading_day.day,
                hour=15,
                minute=20,
                second=0,
                microsecond=0,
            )
            for proposal in exits.create_force_exit_proposals(portfolio, latest_prices, force_time):
                engine.submit_proposal(
                    proposal,
                    risk_engine=risk,
                    portfolio=portfolio,
                    capital=capital,
                    market_data=self.market_data_adapter.snapshot(proposal.symbol, proposal.proposed_price, proposal.timestamp or now),
                    market_clock=exits.market_clock,
                    now=proposal.timestamp or now,
                    idempotency_key=proposal.decision_id,
                )
        if not broker.reconcile():
            capital.mark_portfolio_uncertain()
            raise ReconciliationError("backtest reconciliation failed before settlement")
        capital.settle_trading_day(portfolio)

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
        return sorted(rows, key=lambda row: row[0])

    def _report(self, capital: CapitalGuard, audit: InMemoryAuditLogger, equity_curve: list[Decimal]) -> BacktestReport:
        execution_records = [record for record in audit.records if record.order_id and record.rejection_reason is None]
        exits = [record for record in execution_records if record.decision == TradeSide.SELL.value]
        pnl_values = [record.net_pnl for record in exits]
        wins = [pnl for pnl in pnl_values if pnl > 0]
        losses = [pnl for pnl in pnl_values if pnl < 0]
        rejected: dict[str, int] = {}
        total_costs = money("0")
        slippage = money("0")
        for record in audit.records:
            if record.rejection_reason:
                rejected[record.rejection_reason] = rejected.get(record.rejection_reason, 0) + 1
            total_costs += record.transaction_costs
            slippage += abs(record.slippage)
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
        )

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
