from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from iceberg.capital.guard import CapitalGuard
from iceberg.domain.models import MarketDataSnapshot, OrderExecution, RiskDecision, TradeProposal
from iceberg.execution.brokers import BrokerInterface
from iceberg.logging.audit import InMemoryAuditLogger
from iceberg.market.clock import MarketClock
from iceberg.portfolio.portfolio import Portfolio
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.engine import RiskEngine
from iceberg.risk.permissions import PermissionManager


@dataclass(frozen=True)
class ExecutionResult:
    decision: RiskDecision
    execution: OrderExecution | None


class ExecutionEngine:
    """Coordinator that obtains risk authorization before broker execution."""

    def __init__(
        self,
        broker: BrokerInterface,
        audit_logger: InMemoryAuditLogger,
        emergency_stop: EmergencyStop,
        permissions: PermissionManager,
    ) -> None:
        self.broker = broker
        self.audit_logger = audit_logger
        self.emergency_stop = emergency_stop
        self.permissions = permissions

    def submit_proposal(
        self,
        proposal: TradeProposal,
        *,
        risk_engine: RiskEngine,
        portfolio: Portfolio,
        capital: CapitalGuard,
        market_data: MarketDataSnapshot | None,
        market_clock: MarketClock,
        now: datetime,
        idempotency_key: str,
    ) -> ExecutionResult:
        decision = risk_engine.evaluate(
            proposal,
            portfolio=portfolio,
            capital=capital,
            market_data=market_data,
            permissions=self.permissions,
            emergency_stop=self.emergency_stop,
            market_clock=market_clock,
            now=now,
        )
        if not decision.approved or decision.authorization is None:
            self.audit_logger.log(proposal, decision, None, timestamp=now)
            return ExecutionResult(decision=decision, execution=None)
        execution = self._execute_authorized(proposal, decision, idempotency_key=idempotency_key, now=now)
        return ExecutionResult(decision=decision, execution=execution)

    def _execute_authorized(
        self,
        proposal: TradeProposal,
        decision: RiskDecision,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        execution = self.broker.submit_order(proposal, decision.authorization, idempotency_key, now)
        self.audit_logger.log(proposal, decision, execution, timestamp=now)
        return execution
