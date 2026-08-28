from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from iceberg.domain.models import OrderExecution, RiskDecision, TradeProposal, money


@dataclass
class AuditRecord:
    timestamp: datetime | None
    decision_id: str
    symbol: str
    decision: str
    strategy: str
    market_regime: str | None
    confidence: Decimal | None
    key_signals: tuple[str, ...]
    relevant_features: dict[str, Any]
    quantity: int
    proposed_price: Decimal
    estimated_costs: Decimal
    capital_required: Decimal
    risk_assessment: str
    stop_or_invalidation_level: Decimal | None
    risk_decision: str
    approval_status: str
    rejection_reason: str | None
    order_id: str | None = None
    execution_price: Decimal | None = None
    slippage: Decimal = money("0")
    gross_pnl: Decimal = money("0")
    transaction_costs: Decimal = money("0")
    net_pnl: Decimal = money("0")


@dataclass
class InMemoryAuditLogger:
    records: list[AuditRecord] = field(default_factory=list)

    def log(
        self,
        proposal: TradeProposal,
        decision: RiskDecision,
        execution: OrderExecution | None = None,
        *,
        timestamp: datetime | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            timestamp=timestamp or proposal.timestamp,
            decision_id=proposal.decision_id,
            symbol=proposal.symbol,
            decision=proposal.side.value,
            strategy=proposal.strategy,
            market_regime=proposal.market_regime.value if proposal.market_regime else None,
            confidence=proposal.confidence,
            key_signals=proposal.key_signals,
            relevant_features=proposal.relevant_features,
            quantity=decision.quantity,
            proposed_price=proposal.proposed_price,
            estimated_costs=decision.estimated_costs,
            capital_required=decision.capital_required,
            risk_assessment=decision.risk_assessment,
            stop_or_invalidation_level=proposal.stop_or_invalidation_level,
            risk_decision=decision.rejection_reason or "APPROVED",
            approval_status=decision.approval_status.value,
            rejection_reason=decision.rejection_reason,
        )
        if execution is not None:
            record.order_id = execution.order_id
            record.execution_price = execution.execution_price
            record.slippage = execution.slippage
            record.transaction_costs = execution.transaction_costs
        self.records.append(record)
        return record

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(record) for record in self.records]
