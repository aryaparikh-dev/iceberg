from __future__ import annotations

from abc import ABC, abstractmethod
import copy
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from iceberg.capital.guard import CapitalGuard
from iceberg.domain.enums import OrderStatus, TradeSide
from iceberg.domain.models import OrderExecution, TradeProposal, money
from iceberg.exceptions import AuthorizationError, CapitalInvariantError, LiveTradingDisabledError
from iceberg.execution.authorization import ExecutionAuthorization
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import TransactionCostModel
from iceberg.risk.slippage import FixedBpsSlippageModel, SlippageModel


class BrokerInterface(ABC):
    @abstractmethod
    def submit_order(
        self,
        proposal: TradeProposal,
        authorization: ExecutionAuthorization | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        raise NotImplementedError

    @abstractmethod
    def reconcile(self) -> bool:
        raise NotImplementedError


class PaperBroker(BrokerInterface):
    """Functional paper broker. It never calls a live endpoint."""

    def __init__(
        self,
        portfolio: Portfolio,
        capital: CapitalGuard,
        cost_model: TransactionCostModel,
        *,
        slippage_fraction: Decimal = Decimal("0"),
        slippage_model: SlippageModel | None = None,
        settlement_lag_days: int = 1,
        store=None,
    ) -> None:
        self.portfolio = portfolio
        self.capital = capital
        self.cost_model = cost_model
        self.slippage_fraction = money(slippage_fraction)
        self.slippage_model = slippage_model or FixedBpsSlippageModel(self.slippage_fraction * Decimal("10000"))
        self.settlement_lag_days = settlement_lag_days
        self.store = store
        self._executions_by_idempotency: dict[str, OrderExecution] = store.load_executions_by_idempotency() if store is not None else {}
        self._decision_ids: set[str] = store.load_decision_ids() if store is not None else set()
        self._state_uncertain = False

    def submit_order(
        self,
        proposal: TradeProposal,
        authorization: ExecutionAuthorization | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        if idempotency_key in self._executions_by_idempotency:
            return self._executions_by_idempotency[idempotency_key]
        if proposal.decision_id in self._decision_ids:
            execution = self._rejected(proposal, idempotency_key, "DUPLICATE_DECISION", now)
            self._executions_by_idempotency[idempotency_key] = execution
            self._persist(execution)
            return execution
        if not isinstance(authorization, ExecutionAuthorization):
            execution = self._rejected(proposal, idempotency_key, "RISK_AUTHORIZATION_REQUIRED", now)
            self._executions_by_idempotency[idempotency_key] = execution
            self._persist(execution)
            return execution
        if not authorization.matches(proposal):
            execution = self._rejected(proposal, idempotency_key, "AUTHORIZATION_MISMATCH", now)
            self._executions_by_idempotency[idempotency_key] = execution
            self._persist(execution)
            return execution
        submitted_at = now or authorization.approved_at
        try:
            authorization.validate_session(submitted_at)
        except AuthorizationError as exc:
            execution = self._rejected(proposal, idempotency_key, str(exc), submitted_at)
            self._executions_by_idempotency[idempotency_key] = execution
            self._persist(execution)
            return execution

        snapshot = self._snapshot()
        try:
            with self._transaction():
                authorization.consume_for(proposal, submitted_at)
                self._decision_ids.add(proposal.decision_id)
                price = self._execution_price(proposal, authorization.quantity)
                quantity = authorization.quantity
                cost_breakdown = self.cost_model.estimate(proposal.side, price, quantity)
                costs = cost_breakdown.total
                gross = price * quantity
                gross_pnl = money("0")
                net_pnl = money("0")

                if proposal.side is TradeSide.BUY:
                    required = gross + costs
                    self._assert_final_buy_invariants(proposal.symbol, gross, required)
                    self.capital.apply_buy(proposal.symbol, quantity, price, costs)
                    self.portfolio.record_buy(proposal.symbol, quantity, price)
                    net_flow = -required
                elif proposal.side is TradeSide.SELL:
                    basis = self.portfolio.record_sell(proposal.symbol, quantity, price)
                    net = self.capital.apply_sell(
                        proposal.symbol,
                        quantity,
                        price,
                        costs,
                        cost_basis=basis,
                        proceeds_settle_immediately=self.settlement_lag_days == 0,
                    )
                    gross_pnl = gross - basis
                    net_pnl = net - basis
                    net_flow = net
                else:
                    raise CapitalInvariantError("hold proposals cannot be submitted to broker")

                execution = OrderExecution(
                    order_id=f"PAPER-{uuid4()}",
                    decision_id=proposal.decision_id,
                    idempotency_key=idempotency_key,
                    symbol=proposal.symbol,
                    side=proposal.side,
                    quantity=quantity,
                    execution_price=price,
                    gross_value=gross,
                    transaction_costs=costs,
                    net_cash_flow=net_flow,
                    timestamp=now,
                    status=OrderStatus.FILLED.value,
                    slippage=price - proposal.proposed_price,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    charge_schedule_version=cost_breakdown.schedule_version,
                )
                self._executions_by_idempotency[idempotency_key] = execution
                self._persist(execution)
                return execution
        except Exception as exc:
            self._restore(snapshot)
            execution = self._rejected(proposal, idempotency_key, f"EXECUTION_FAIL_CLOSED:{exc}", now)
            self._executions_by_idempotency[idempotency_key] = execution
            try:
                self._persist(execution)
            except Exception:
                pass
            return execution

    def _assert_final_buy_invariants(self, symbol: str, gross: Decimal, required: Decimal) -> None:
        current_cost_basis = self.portfolio.gross_cost_basis(symbol)
        if current_cost_basis + gross > self.capital.max_single_stock_value():
            raise CapitalInvariantError("final fill breaches stock allocation limit")
        portfolio_limit = (
            self.capital.state.daily_starting_capital
            * self.capital.settings.capital.maximum_portfolio_allocation
        )
        if self.capital.state.deployed_capital + gross > portfolio_limit:
            raise CapitalInvariantError("final fill breaches portfolio allocation limit")
        if required > self.capital.spendable_cash():
            raise CapitalInvariantError("final fill exceeds spendable cash")
        if (
            not self.capital.settings.capital.leverage_allowed
            and self.capital.state.available_cash - required < 0
        ):
            raise CapitalInvariantError("final fill would create leverage")

    def reconcile(self) -> bool:
        if self._state_uncertain:
            self.capital.mark_broker_state_unknown()
            return False
        if self.store is not None:
            persisted_positions = self.store.load_positions()
            if persisted_positions != self.portfolio.positions:
                self.capital.mark_portfolio_uncertain()
                self.store.save_reconciliation_status(
                    portfolio_state=self.capital.state.portfolio_state,
                    broker_state_known=self.capital.state.broker_state_known,
                    reason="portfolio mismatch",
                    updated_at=None,
                )
                return False
        self.capital.state.broker_state_known = True
        if self.capital.state.broker_available_cash is None:
            self.capital.state.broker_available_cash = self.capital.state.settled_cash
        self.capital.persist()
        return True

    def mark_state_uncertain(self, reason: str) -> None:
        self._state_uncertain = True
        self.capital.mark_portfolio_uncertain()
        if self.store is not None:
            self.store.save_reconciliation_status(
                portfolio_state=self.capital.state.portfolio_state,
                broker_state_known=self.capital.state.broker_state_known,
                reason=reason,
                updated_at=None,
            )

    def _execution_price(self, proposal: TradeProposal, quantity: int) -> Decimal:
        return self.slippage_model.execution_price(proposal.side, proposal.proposed_price, quantity)

    def _rejected(self, proposal: TradeProposal, idempotency_key: str, reason: str | None, now: datetime | None) -> OrderExecution:
        return OrderExecution(
            order_id=f"REJECTED-{uuid4()}",
            decision_id=proposal.decision_id,
            idempotency_key=idempotency_key,
            symbol=proposal.symbol,
            side=proposal.side,
            quantity=0,
            execution_price=proposal.proposed_price,
            gross_value=money("0"),
            transaction_costs=money("0"),
            net_cash_flow=money("0"),
            timestamp=now,
            status=OrderStatus.REJECTED.value,
            rejection_reason=reason,
            gross_pnl=money("0"),
            net_pnl=money("0"),
            charge_schedule_version="none",
        )

    def _snapshot(self):
        return (
            copy.deepcopy(self.capital.state),
            copy.deepcopy(self.portfolio.positions),
            copy.deepcopy(self._executions_by_idempotency),
            copy.deepcopy(self._decision_ids),
        )

    def _restore(self, snapshot) -> None:
        capital_state, positions, idempotency, decision_ids = snapshot
        self.capital.state = capital_state
        self.portfolio.positions = positions
        self._executions_by_idempotency = idempotency
        self._decision_ids = decision_ids

    def _persist(self, execution: OrderExecution) -> None:
        if self.store is None:
            return
        self.store.save_capital_state(self.capital.state)
        self.store.save_positions(self.portfolio.positions)
        self.store.save_execution(execution)
        self.store.save_reconciliation_status(
            portfolio_state=self.capital.state.portfolio_state,
            broker_state_known=self.capital.state.broker_state_known,
            reason=execution.rejection_reason,
            updated_at=execution.timestamp,
        )

    def _transaction(self):
        if self.store is None:
            return _NullTransaction()
        return self.store.transaction()


class _NullTransaction:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class LiveBrokerStub(BrokerInterface):
    def submit_order(
        self,
        proposal: TradeProposal,
        authorization: ExecutionAuthorization | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        raise LiveTradingDisabledError("live trading is disabled in Version 1")

    def reconcile(self) -> bool:
        raise LiveTradingDisabledError("live broker reconciliation is disabled in Version 1")
