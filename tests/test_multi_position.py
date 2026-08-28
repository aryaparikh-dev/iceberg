from iceberg.domain.models import TradeProposal
from iceberg.execution.brokers import PaperBroker
from iceberg.execution.engine import ExecutionEngine
from iceberg.logging.audit import InMemoryAuditLogger
from iceberg.risk.costs import FixedTransactionCostModel

from tests.conftest import D, market_snapshot


def test_multiple_positions_stop_before_transaction_costs_create_negative_cash(safe_context):
    safe_context.settings.risk.maximum_positions = 20
    safe_context.risk.cost_model = FixedTransactionCostModel(buy_cost=D("0.10"))
    broker = PaperBroker(
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        cost_model=safe_context.risk.cost_model,
    )
    engine = ExecutionEngine(
        broker=broker,
        audit_logger=InMemoryAuditLogger(),
        emergency_stop=safe_context.emergency_stop,
        permissions=safe_context.permissions,
    )

    approvals = 0
    for idx in range(10):
        symbol = f"STK{idx}"
        proposal = TradeProposal.buy(symbol, price=D("10"), decision_id=f"d-{idx}")
        result = engine.submit_proposal(
            proposal,
            risk_engine=safe_context.risk,
            portfolio=safe_context.portfolio,
            capital=safe_context.guard,
            market_data=market_snapshot(symbol, "10", safe_context.now),
            market_clock=safe_context.clock,
            now=safe_context.now,
            idempotency_key=f"k-{idx}",
        )
        if result.decision.approved:
            approvals += 1

    assert approvals == 9
    assert safe_context.guard.state.available_cash == D("9.10")
    assert safe_context.guard.state.available_cash >= 0
    assert len(safe_context.portfolio.positions) == 9
