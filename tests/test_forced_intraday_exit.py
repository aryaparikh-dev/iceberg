from iceberg.execution.exit_manager import ExitManager

from tests.conftest import D, ist_datetime


def test_force_exit_window_creates_exit_proposals(safe_context):
    safe_context.portfolio.record_buy("ABC", 2, D("10"))
    manager = ExitManager(safe_context.clock)

    proposals = manager.create_force_exit_proposals(safe_context.portfolio, {"ABC": D("10")}, ist_datetime(15, 20))

    assert len(proposals) == 1
    assert proposals[0].symbol == "ABC"
    assert proposals[0].quantity == 2


def test_missing_forced_exit_by_deadline_marks_state_uncertain(safe_context):
    safe_context.portfolio.record_buy("ABC", 1, D("10"))
    manager = ExitManager(safe_context.clock)

    manager.mark_uncertain_after_deadline(safe_context.portfolio, safe_context.guard, ist_datetime(15, 26))

    assert safe_context.guard.state.portfolio_state == "UNCERTAIN"
