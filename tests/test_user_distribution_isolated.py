from iceberg.capital.manager import CapitalManager

from tests.conftest import D, ist_datetime


def test_user_distribution_never_returns_to_ai_capital(safe_context):
    safe_context.guard.state.available_cash = D("500")
    safe_context.guard.state.settled_cash = D("500")
    safe_context.guard.state.broker_available_cash = D("500")
    safe_context.guard.settle_trading_day(safe_context.portfolio)
    assert safe_context.guard.state.user_distribution == D("200")

    manager = CapitalManager(safe_context.guard, None, safe_context.settings, safe_context.calendar)
    manager.start_trading_day(ist_datetime(9, 0, day=6).date(), ist_datetime(9, 0, day=6))

    assert safe_context.guard.state.daily_starting_capital == D("300")
    assert safe_context.guard.state.user_distribution == D("200")
