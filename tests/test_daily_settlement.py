import pytest

from tests.conftest import D


@pytest.mark.parametrize(
    ("ending_equity", "distribution", "next_capital"),
    [
        ("105", "0", "105"),
        ("110", "0", "110"),
        ("111", "5.50", "105.50"),
        ("500", "200", "300"),
        ("80", "0", "80"),
    ],
)
def test_daily_profit_sharing_examples_are_strictly_greater_than_ten_percent(safe_context, ending_equity, distribution, next_capital):
    result = safe_context.guard.settle_trading_day(D(ending_equity), positions_flat=True)

    assert result.user_distribution == D(distribution)
    assert result.next_day_capital == D(next_capital)
    assert safe_context.guard.state.user_distribution == D(distribution)
    assert safe_context.guard.state.next_day_capital == D(next_capital)
