from __future__ import annotations

from datetime import datetime

from iceberg.domain.enums import Permission
from iceberg.domain.models import OrderExecution, RiskDecision, TradeProposal
from iceberg.execution.brokers import BrokerInterface
from iceberg.logging.audit import InMemoryAuditLogger
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.permissions import PermissionManager


class ExecutionEngine:
    """Final permission gate before a broker receives a risk-approved order."""

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

    def execute(
        self,
        proposal: TradeProposal,
        decision: RiskDecision,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> OrderExecution:
        if not self.permissions.has(Permission.PAPER_TRADE):
            decision = RiskDecision(
                approved=False,
                decision_id=proposal.decision_id,
                symbol=proposal.symbol,
                side=proposal.side,
                rejection_reason="PERMISSION_DENIED",
            )
        elif self.emergency_stop.blocks(proposal.side):
            decision = RiskDecision(
                approved=False,
                decision_id=proposal.decision_id,
                symbol=proposal.symbol,
                side=proposal.side,
                rejection_reason="EMERGENCY_STOP",
            )
        execution = self.broker.submit_order(proposal, decision, idempotency_key, now)
        self.audit_logger.log(proposal, decision, execution, timestamp=now)
        return execution
