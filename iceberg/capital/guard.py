from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN

from iceberg.config.settings import Settings, default_settings
from iceberg.domain.enums import Permission
from iceberg.domain.models import money, require_aware
from iceberg.exceptions import CapitalInvariantError, FailClosedError, ReconciliationError
from iceberg.security.auth import AuthorizationContext


_CAPITAL_MANAGER_TOKEN = object()


@dataclass(frozen=True)
class DailySettlement:
    profit: Decimal
    profit_percentage: Decimal
    user_distribution: Decimal
    next_day_capital: Decimal


@dataclass
class CapitalState:
    starting_capital: Decimal
    daily_starting_capital: Decimal
    available_cash: Decimal
    broker_available_cash: Decimal | None
    settled_cash: Decimal
    unsettled_cash: Decimal
    deployed_capital: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    market_value: Decimal
    total_equity: Decimal
    user_distribution: Decimal
    next_day_capital: Decimal
    current_trading_date: date | None = None
    snapshot_created_at: datetime | None = None
    consecutive_losses: int = 0
    broker_state_known: bool = True
    portfolio_state: str = "READY"


class CapitalGuard:
    """The single authoritative capital-control boundary for all engines."""

    def __init__(self, state: CapitalState, settings: Settings | None = None, store=None) -> None:
        self.settings = settings or default_settings()
        self.state = state
        self.store = store
        self._snapshot_locked_dates: set[date] = set(store.locked_snapshot_dates()) if store is not None else set()
        self._assert_invariants()

    @classmethod
    def initial(cls, starting_capital: Decimal | int | str = Decimal("100"), settings: Settings | None = None, store=None) -> "CapitalGuard":
        if store is not None:
            account_exists = False
            if hasattr(store, "account_state_exists"):
                account_exists = store.account_state_exists()
            elif hasattr(store, "load_capital_state"):
                account_exists = store.load_capital_state() is not None
            if account_exists:
                raise ReconciliationError("persisted account state already exists; use CapitalGuard.load(store)")
        starting = money(starting_capital)
        if starting <= 0:
            raise CapitalInvariantError("starting capital must be positive")
        state = CapitalState(
            starting_capital=starting,
            daily_starting_capital=starting,
            available_cash=starting,
            broker_available_cash=starting,
            settled_cash=starting,
            unsettled_cash=money("0"),
            deployed_capital=money("0"),
            realized_pnl=money("0"),
            unrealized_pnl=money("0"),
            market_value=money("0"),
            total_equity=starting,
            user_distribution=money("0"),
            next_day_capital=starting,
        )
        guard = cls(state, settings=settings, store=store)
        guard.persist()
        return guard

    @classmethod
    def load(cls, store, settings: Settings | None = None) -> "CapitalGuard":
        state = store.load_capital_state()
        if state is None:
            raise ReconciliationError("no persisted capital state found")
        return cls(state, settings=settings, store=store)

    def persist(self) -> None:
        if self.store is not None:
            self.store.save_capital_state(self.state)

    def create_daily_snapshot(self, trading_date: date, snapshot_time: datetime) -> bool:
        return self._create_daily_snapshot(
            trading_date,
            snapshot_time,
            capital_amount=self.state.next_day_capital,
            authority_token=_CAPITAL_MANAGER_TOKEN,
        )

    def _create_daily_snapshot(
        self,
        trading_date: date,
        snapshot_time: datetime,
        *,
        capital_amount: Decimal,
        authority_token: object,
    ) -> bool:
        if authority_token is not _CAPITAL_MANAGER_TOKEN:
            raise PermissionError("daily capital snapshots must be created by CapitalManager")
        require_aware(snapshot_time, "snapshot_time")
        if trading_date in self._snapshot_locked_dates:
            return False
        amount = money(capital_amount)
        if amount < 0:
            raise CapitalInvariantError("daily capital snapshot cannot be negative")
        if self.store is not None and not self.store.save_daily_snapshot(trading_date, snapshot_time, amount):
            self._snapshot_locked_dates.add(trading_date)
            return False
        self.state.daily_starting_capital = amount
        self.state.available_cash = amount
        self.state.broker_available_cash = amount
        self.state.settled_cash = amount
        self.state.unsettled_cash = money("0")
        self.state.deployed_capital = money("0")
        self.state.market_value = money("0")
        self.state.realized_pnl = money("0")
        self.state.unrealized_pnl = money("0")
        self.state.total_equity = amount
        self.state.next_day_capital = amount
        self.state.current_trading_date = trading_date
        self.state.snapshot_created_at = snapshot_time
        self.state.broker_state_known = True
        self.state.portfolio_state = "READY"
        self._snapshot_locked_dates.add(trading_date)
        self._assert_invariants()
        self.persist()
        return True

    def max_single_stock_value(self) -> Decimal:
        return self.state.daily_starting_capital * self.settings.capital.maximum_stock_allocation

    def max_whole_shares_for_price(self, execution_price: Decimal, current_symbol_cost_basis: Decimal = Decimal("0")) -> int:
        price = money(execution_price)
        if price <= 0:
            return 0
        remaining = self.max_single_stock_value() - money(current_symbol_cost_basis)
        if remaining < price:
            return 0
        return int((remaining / price).to_integral_value(rounding=ROUND_DOWN))

    def spendable_cash(self) -> Decimal:
        if not self.state.broker_state_known or self.state.broker_available_cash is None:
            raise FailClosedError("broker cash state unknown")
        return min(self.state.available_cash, self.state.broker_available_cash)

    def mark_broker_state_unknown(self) -> None:
        self.state.broker_state_known = False
        self.state.broker_available_cash = None
        self.persist()

    def mark_portfolio_uncertain(self) -> None:
        self.state.portfolio_state = "UNCERTAIN"
        self.mark_broker_state_unknown()

    def apply_buy(self, symbol: str, quantity: int, execution_price: Decimal, transaction_costs: Decimal) -> None:
        if quantity <= 0:
            raise CapitalInvariantError("buy quantity must be positive")
        gross = money(execution_price) * quantity
        costs = money(transaction_costs)
        total = gross + costs
        if total > self.spendable_cash():
            raise CapitalInvariantError("buy would make cash negative or exceed broker cash")
        self.state.available_cash -= total
        if self.state.broker_available_cash is not None:
            self.state.broker_available_cash -= total
        self.state.settled_cash -= total
        self.state.deployed_capital += gross
        self.state.market_value += gross
        self._recompute_total_equity()
        self._assert_invariants()
        self.persist()

    def apply_sell(
        self,
        symbol: str,
        quantity: int,
        execution_price: Decimal,
        transaction_costs: Decimal,
        *,
        cost_basis: Decimal,
        proceeds_settle_immediately: bool,
    ) -> Decimal:
        if quantity <= 0:
            raise CapitalInvariantError("sell quantity must be positive")
        gross = money(execution_price) * quantity
        costs = money(transaction_costs)
        net = gross - costs
        if net < 0:
            raise CapitalInvariantError("sale costs exceed gross proceeds")
        basis = money(cost_basis)
        self.state.available_cash += net
        self.state.deployed_capital = max(money("0"), self.state.deployed_capital - basis)
        self.state.market_value = max(money("0"), self.state.market_value - basis)
        trade_pnl = net - basis
        self.state.realized_pnl += trade_pnl
        if trade_pnl < 0:
            self.state.consecutive_losses += 1
        elif trade_pnl > 0:
            self.state.consecutive_losses = 0
        if proceeds_settle_immediately:
            self.state.settled_cash += net
            if self.state.broker_available_cash is not None:
                self.state.broker_available_cash += net
        else:
            self.state.unsettled_cash += net
        self._recompute_total_equity()
        self._assert_invariants()
        self.persist()
        return net

    def settle_unsettled_cash(self) -> None:
        amount = self.state.unsettled_cash
        self.state.unsettled_cash = money("0")
        self.state.settled_cash += amount
        if self.state.broker_available_cash is not None:
            self.state.broker_available_cash += amount
        self._assert_invariants()
        self.persist()

    def update_mark_to_market(self, market_value: Decimal, unrealized_pnl: Decimal | None = None) -> None:
        self.state.market_value = money(market_value)
        if unrealized_pnl is not None:
            self.state.unrealized_pnl = money(unrealized_pnl)
        self._recompute_total_equity()
        self._assert_invariants()
        self.persist()

    def calculate_daily_settlement(self, ending_equity: Decimal) -> DailySettlement:
        ending = money(ending_equity)
        profit = ending - self.state.daily_starting_capital
        profit_percentage = money("0") if self.state.daily_starting_capital == 0 else profit / self.state.daily_starting_capital
        if profit_percentage > self.settings.settlement.profit_sharing_threshold:
            distribution = profit * self.settings.settlement.user_profit_fraction_above_threshold
        else:
            distribution = money("0")
        distribution = distribution.quantize(Decimal("0.01"))
        return DailySettlement(profit, profit_percentage, distribution, ending - distribution)

    def settle_trading_day(self, portfolio) -> DailySettlement:
        if self.state.portfolio_state == "UNCERTAIN" or not self.state.broker_state_known:
            raise ReconciliationError("cannot settle while reconciliation state is uncertain")
        if not portfolio.is_flat():
            self.mark_portfolio_uncertain()
            raise ReconciliationError("daily settlement requires confirmed flat intraday portfolio")
        if self.state.broker_available_cash is None:
            raise ReconciliationError("broker cash must be known before settlement")
        if self.state.available_cash != self.state.settled_cash + self.state.unsettled_cash:
            self.mark_portfolio_uncertain()
            raise ReconciliationError("cash settlement components do not reconcile")
        settlement = self.calculate_daily_settlement(self.state.available_cash)
        next_capital = settlement.next_day_capital
        self.state.user_distribution += settlement.user_distribution
        self.state.next_day_capital = next_capital
        self.state.available_cash = next_capital
        self.state.broker_available_cash = next_capital
        self.state.settled_cash = next_capital
        self.state.unsettled_cash = money("0")
        self.state.deployed_capital = money("0")
        self.state.market_value = money("0")
        self.state.realized_pnl = money("0")
        self.state.unrealized_pnl = money("0")
        self.state.total_equity = next_capital
        self._assert_invariants()
        self.persist()
        return settlement

    def reset_consecutive_losses(self, context: AuthorizationContext) -> None:
        context.require(Permission.CAPITAL_ADMIN)
        self.state.consecutive_losses = 0
        self.persist()

    def _recompute_total_equity(self) -> None:
        self.state.total_equity = self.state.available_cash + self.state.market_value

    def _assert_invariants(self) -> None:
        if self.state.available_cash < 0:
            raise CapitalInvariantError("available_cash invariant violated")
        if self.state.settled_cash < 0:
            raise CapitalInvariantError("settled_cash invariant violated")
        if self.state.broker_available_cash is not None and self.state.broker_available_cash < 0:
            raise CapitalInvariantError("broker_available_cash invariant violated")
        if self.state.deployed_capital < 0:
            raise CapitalInvariantError("deployed_capital invariant violated")
        permitted_base = max(self.state.daily_starting_capital, self.state.next_day_capital)
        permitted_total = permitted_base + self.state.realized_pnl + self.state.unrealized_pnl
        if self.state.deployed_capital + self.state.available_cash > permitted_total + Decimal("0.000001"):
            # Transaction costs can lower equity; the combined value should never exceed permitted accounting capital.
            raise CapitalInvariantError("capital conservation invariant violated")
