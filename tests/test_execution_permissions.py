from iceberg.domain.enums import Permission
from iceberg.domain.models import TradeProposal

from tests.conftest import D, market_snapshot


def test_default_ai_permissions_exclude_money_movement_and_live_trading(safe_context):
    assert safe_context.permissions.has(Permission.MARKET_DATA_READ)
    assert safe_context.permissions.has(Permission.PORTFOLIO_READ)
    assert safe_context.permissions.has(Permission.PAPER_TRADE)
    assert not safe_context.permissions.has(Permission.LIVE_TRADE)
    assert not safe_context.permissions.has(Permission.WITHDRAW_FUNDS)
    assert not safe_context.permissions.has(Permission.BANK_ACCESS)
    assert not safe_context.permissions.has(Permission.EXTERNAL_TRANSFER)
    assert not safe_context.permissions.has(Permission.CAPITAL_ADMIN)
    assert not safe_context.permissions.has(Permission.FUNDING_CONFIRM)


def test_missing_paper_trade_permission_rejects_execution_path(safe_context):
    safe_context.permissions.revoke(Permission.PAPER_TRADE)
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="permission")

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_snapshot("ABC", "10", safe_context.now),
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "PERMISSION_DENIED"
