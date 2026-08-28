from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from iceberg.ai.regime import RegimeDetector
from iceberg.capital.guard import CapitalGuard
from iceberg.config.settings import Settings, default_settings
from iceberg.data.validation import DataValidator
from iceberg.domain.models import Candle, MarketDataSnapshot, money
from iceberg.execution.brokers import PaperBroker
from iceberg.execution.engine import ExecutionEngine
from iceberg.logging.audit import InMemoryAuditLogger
from iceberg.market.calendar import TradingCalendar
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import FixedTransactionCostModel, TransactionCostModel
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.engine import RiskEngine
from iceberg.risk.permissions import PermissionManager
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
    maximum_drawdown: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None
    transaction_costs: Decimal
    slippage: Decimal
    user_distributions: Decimal
    final_ai_capital: Decimal
    rejected_trades: int
    rejection_reasons: dict[str, int] = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        cost_model: TransactionCostModel | None = None,
        calendar: TradingCalendar | None = None,
    ) -> None:
        self.settings = settings or default_settings()
        self.cost_model = cost_model or FixedTransactionCostModel()
        self.calendar = calendar or TradingCalendar(provider_verified=True)

    def run(self, candles_by_symbol: dict[str, list[Candle]], strategy: Strategy) -> BacktestReport:
        capital = CapitalGuard.initial(self.settings.capital.initial_capital_inr, settings=self.settings)
        portfolio = Portfolio()
        permissions = PermissionManager.default_ai()
        emergency_stop = EmergencyStop(active=False)
        clock = MarketClock(self.calendar, self.settings.market)
        risk = RiskEngine(self.settings, self.cost_model)
        audit = InMemoryAuditLogger()
        broker = PaperBroker(portfolio, capital, self.cost_model, settlement_lag_days=0)
        engine = ExecutionEngine(broker, audit, emergency_stop, permissions)
        regime_detector = RegimeDetector()
        validator = DataValidator(self.settings.data.max_market_data_age)

        timeline = self._timeline(candles_by_symbol)
        if timeline:
            first_timestamp = timeline[0][0]
            capital.create_daily_snapshot(
                first_timestamp.date(),
                first_timestamp.replace(hour=9, minute=0, second=0, microsecond=0),
            )
        equity_curve = [capital.state.total_equity]
        histories: dict[str, list[Candle]] = {symbol.upper(): [] for symbol in candles_by_symbol}

        for now, symbol, candle in timeline:
            symbol = symbol.upper()
            histories[symbol].append(candle)
            validator.validate_candles(histories[symbol], expected_symbol=symbol, now=now)
            regime = regime_detector.detect(histories[symbol])
            proposals = strategy.generate(symbol, tuple(histories[symbol]), now, regime)
            for proposal in proposals:
                if proposal.side.value == "HOLD":
                    audit.log(proposal, risk.reject("HOLD_NO_EXECUTION", proposal), timestamp=now)
                    continue
                market_data = MarketDataSnapshot(
                    symbol=symbol,
                    last_price=candle.close,
                    timestamp=now,
                    average_volume=max(candle.volume, Decimal("100000")),
                    average_traded_value=max(candle.volume * candle.close, Decimal("10000000")),
                    bid_ask_spread_fraction=Decimal("0.001"),
                    recent_activity=True,
                    estimated_price_impact_fraction=Decimal("0.001"),
                    abnormal_volatility=False,
                )
                decision = risk.evaluate(
                    proposal,
                    portfolio=portfolio,
                    capital=capital,
                    market_data=market_data,
                    permissions=permissions,
                    emergency_stop=emergency_stop,
                    market_clock=clock,
                    now=now,
                )
                engine.execute(proposal, decision, idempotency_key=proposal.decision_id, now=now)
            mark_value = portfolio.total_market_value({symbol: candle.close})
            capital.update_mark_to_market(mark_value)
            equity_curve.append(capital.state.total_equity)

        return self._report(capital, audit, equity_curve)

    def _timeline(self, candles_by_symbol: dict[str, list[Candle]]) -> list[tuple[datetime, str, Candle]]:
        rows: list[tuple[datetime, str, Candle]] = []
        for symbol, candles in candles_by_symbol.items():
            for candle in sorted(candles, key=lambda c: c.timestamp):
                rows.append((candle.timestamp, symbol.upper(), candle))
        return sorted(rows, key=lambda row: row[0])

    def _report(self, capital: CapitalGuard, audit: InMemoryAuditLogger, equity_curve: list[Decimal]) -> BacktestReport:
        executions = [record for record in audit.records if record.order_id]
        rejected: dict[str, int] = {}
        total_costs = money("0")
        slippage = money("0")
        for record in audit.records:
            if record.rejection_reason:
                rejected[record.rejection_reason] = rejected.get(record.rejection_reason, 0) + 1
            total_costs += record.transaction_costs
            slippage += record.slippage
        starting = capital.state.starting_capital
        ending = capital.state.total_equity
        net_profit = ending - starting
        max_drawdown = self._max_drawdown(equity_curve)
        return BacktestReport(
            starting_capital=starting,
            ending_capital=ending,
            net_profit=net_profit,
            return_percentage=money("0") if starting == 0 else net_profit / starting,
            trades=len(executions),
            winning_trades=0,
            losing_trades=0,
            win_rate=money("0"),
            average_win=money("0"),
            average_loss=money("0"),
            profit_factor=None,
            maximum_drawdown=max_drawdown,
            sharpe=None,
            sortino=None,
            transaction_costs=total_costs,
            slippage=slippage,
            user_distributions=capital.state.user_distribution,
            final_ai_capital=capital.state.next_day_capital,
            rejected_trades=sum(rejected.values()),
            rejection_reasons=rejected,
        )

    def _max_drawdown(self, equity_curve: list[Decimal]) -> Decimal:
        peak = equity_curve[0] if equity_curve else money("0")
        max_dd = money("0")
        for point in equity_curve:
            peak = max(peak, point)
            if peak:
                max_dd = max(max_dd, (peak - point) / peak)
        return max_dd
