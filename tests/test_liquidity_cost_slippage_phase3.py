from datetime import date

from iceberg.data.models import HistoricalBar
from iceberg.domain.enums import TradeSide
from iceberg.domain.models import TradeProposal
from iceberg.risk.costs import NSEIntradayCharges
from iceberg.risk.liquidity import HistoricalLiquidityModel
from iceberg.risk.slippage import VolumeParticipationSlippageModel, VolatilityAwareSlippageModel

from tests.conftest import D, ist_datetime, market_snapshot


def historical_bar(minute, volume, close="10"):
    return HistoricalBar(
        symbol="ABC",
        exchange="NSE",
        timestamp=ist_datetime(10, minute),
        open=D(close),
        high=D(close),
        low=D(close),
        close=D(close),
        volume=D(volume),
        interval="1m",
        source_id="unit",
        ingested_at=ist_datetime(8, 0),
    )


def test_rolling_liquidity_uses_past_only():
    bars = [historical_bar(0, "100"), historical_bar(1, "10000")]

    snapshot = HistoricalLiquidityModel(lookback_bars=20).snapshot(bars, symbol="ABC", as_of=ist_datetime(10, 0))

    assert snapshot.lookback_bars == 1
    assert snapshot.average_daily_volume == D("100")
    assert snapshot.observed_volume == D("100")


def test_participation_rate_limit_rejects_unrealistic_backtest_quantity(safe_context):
    proposal = TradeProposal.buy("ABC", price=D("10"), decision_id="participation", quantity=2)
    market_data = market_snapshot("ABC", "10", safe_context.now, observed_volume=D("100"))

    decision = safe_context.risk.evaluate(
        proposal,
        portfolio=safe_context.portfolio,
        capital=safe_context.guard,
        market_data=market_data,
        permissions=safe_context.permissions,
        emergency_stop=safe_context.emergency_stop,
        market_clock=safe_context.clock,
        now=safe_context.now,
    )

    assert not decision.approved
    assert decision.rejection_reason == "PARTICIPATION_RATE_LIMIT"


def test_transaction_cost_schedule_metadata_requires_source_for_verified_schedule():
    charges = NSEIntradayCharges(
        brokerage_flat=D("1"),
        stt_sell_rate=D("0.00025"),
        exchange_txn_rate=D("0.0000322"),
        sebi_rate=D("0.000001"),
        stamp_duty_buy_rate=D("0.00003"),
        gst_rate=D("0.18"),
        schedule_version="example-2026",
        schedule_name="example-explicit-nse-cash",
        effective_from=date(2026, 1, 1),
        source_reference="internal-test-fixture",
        verified=True,
    )

    assert charges.metadata()["schedule_name"] == "example-explicit-nse-cash"
    assert charges.metadata()["verified"] is True
    assert charges.metadata()["effective_from"] == "2026-01-01"


def test_volume_participation_slippage_uses_quantity_and_volume():
    model = VolumeParticipationSlippageModel(
        observed_volume=D("100"),
        base_basis_points=D("0"),
        participation_basis_points=D("100"),
    )

    assert model.execution_price(TradeSide.BUY, D("100"), 10) == D("100.100")


def test_volatility_aware_slippage_uses_volatility_fraction():
    model = VolatilityAwareSlippageModel(volatility_fraction=D("0.02"), volatility_multiplier=D("0.50"))

    assert model.execution_price(TradeSide.SELL, D("100"), 1) == D("99.00")
