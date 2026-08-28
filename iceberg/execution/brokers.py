from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from iceberg.capital.guard import CapitalGuard
from iceberg.domain.enums import OrderStatus, TradeSide
from iceberg.domain.models import OrderExecution, RiskDecision, TradeProposal, money
from iceberg.exceptions import CapitalInvariantError, DuplicateDecisionError, LiveTradingDisabledError
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.costs import TransactionCostModel


class BrokerInterface(ABC):
    @abstractmethod
    def submit_order(
        self,
        proposal: TradeProposal,
        decision: RiskDecision | None,
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
        settlement_lag_days: int = 1,
    ) -> None:
        self.portfolio = portfolio
        self.capital = capital
        self.cost_model = cost_model
        self.slippage_fraction = money(slippage_fraction)
        self.settlement_lag_days = settlement_lag_days
        self._executions_by_idempotency: dict[str, OrderExecution] = {}
        self._decision_ids: set[str] = set()
        self._state_uncertain = False

    def submit_order(
        self,
        proposal: TradeProposal,
        decision: RiskDecision | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        if idempotency_key in self._executions_by_idempotency:
            return self._executions_by_idempotency[idempotency_key]
        if proposal.decision_id in self._decision_ids:
            execution = self._rejected(proposal, idempotency_key, "DUPLICATE_DECISION", now)
            self._executions_by_idempotency[idempotency_key] = execution
            return execution
        if decision is None or not decision.approved:
            execution = self._rejected(proposal, idempotency_key, (decision.rejection_reason if decision else "RISK_NOT_APPROVED"), now)
            self._executions_by_idempotency[idempotency_key] = execution
            return execution
        if decision.quantity <= 0:
            execution = self._rejected(proposal, idempotency_key, "INVALID_QUANTITY", now)
            self._executions_by_idempotency[idempotency_key] = execution
            return execution

        self._decision_ids.add(proposal.decision_id)
        price = self._execution_price(proposal)
        quantity = decision.quantity
        try:
            costs = self.cost_model.estimate(proposal.side, price, quantity).total
            gross = price * quantity
            if proposal.side is TradeSide.BUY:
                required = gross + costs
                if required > self.capital.spendable_cash():
                    raise CapitalInvariantError("approved buy no longer fits cash")
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
                net_flow = net
            else:
                execution = self._rejected(proposal, idempotency_key, "NO_EXECUTION_FOR_HOLD", now)
                self._executions_by_idempotency[idempotency_key] = execution
                return execution
        except Exception as exc:
            execution = self._rejected(proposal, idempotency_key, f"EXECUTION_FAIL_CLOSED:{exc}", now)
            self._executions_by_idempotency[idempotency_key] = execution
            return execution

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
        )
        self._executions_by_idempotency[idempotency_key] = execution
        return execution

    def reconcile(self) -> bool:
        if self._state_uncertain:
            self.capital.mark_broker_state_unknown()
            return False
        self.capital.state.broker_state_known = True
        if self.capital.state.broker_available_cash is None:
            self.capital.state.broker_available_cash = self.capital.state.settled_cash
        return True

    def mark_state_uncertain(self, reason: str) -> None:
        self._state_uncertain = True
        self.capital.mark_portfolio_uncertain()

    def _execution_price(self, proposal: TradeProposal) -> Decimal:
        if proposal.side is TradeSide.BUY:
            return proposal.proposed_price * (Decimal("1") + self.slippage_fraction)
        if proposal.side is TradeSide.SELL:
            return proposal.proposed_price * (Decimal("1") - self.slippage_fraction)
        return proposal.proposed_price

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
        )


class LiveBrokerStub(BrokerInterface):
    def submit_order(
        self,
        proposal: TradeProposal,
        decision: RiskDecision | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        raise LiveTradingDisabledError("live trading is disabled in Version 1")

    def reconcile(self) -> bool:
        raise LiveTradingDisabledError("live broker reconciliation is disabled in Version 1")
