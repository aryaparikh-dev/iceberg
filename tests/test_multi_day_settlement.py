from iceberg.capital.manager import CapitalManager

from tests.conftest import D, ist_datetime


def test_multi_day_snapshot_uses_prior_next_day_capital(safe_context):
    safe_context.guard.state.available_cash = D("111")
    safe_context.guard.state.settled_cash = D("111")
    safe_context.guard.state.broker_available_cash = D("111")
    safe_context.guard.settle_trading_day(safe_context.portfolio)
    manager = CapitalManager(
        capital=safe_context.guard,
        funding_ledger=None,
        settings=safe_context.settings,
        calendar=safe_context.calendar,
    )

    manager.start_trading_day(ist_datetime(9, 0, day=6).date(), ist_datetime(9, 0, day=6))

    assert safe_context.guard.state.daily_starting_capital == D("105.50")
    assert safe_context.guard.state.available_cash == D("105.50")
