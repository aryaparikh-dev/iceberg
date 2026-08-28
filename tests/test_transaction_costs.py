from iceberg.domain.enums import TradeSide
from iceberg.risk.costs import FixedTransactionCostModel, NSEIntradayCostModel, NSEIntradayCharges

from tests.conftest import D


def test_fixed_cost_model_applies_buy_and_sell_costs():
    model = FixedTransactionCostModel(buy_cost=D("1.25"), sell_cost=D("0.75"))

    assert model.estimate(TradeSide.BUY, D("10"), 2).total == D("1.25")
    assert model.estimate(TradeSide.SELL, D("10"), 2).total == D("0.75")
    assert model.net_sale_proceeds(D("10"), 2) == D("19.25")


def test_nse_intraday_cost_model_is_configurable_and_decimal_based():
    model = NSEIntradayCostModel(
        NSEIntradayCharges(
            brokerage_flat=D("1"),
            stt_sell_rate=D("0.00025"),
            exchange_txn_rate=D("0.0000322"),
            sebi_rate=D("0.000001"),
            stamp_duty_buy_rate=D("0.00003"),
            gst_rate=D("0.18"),
            schedule_version="test-config",
        )
    )

    buy = model.estimate(TradeSide.BUY, D("100"), 1)
    sell = model.estimate(TradeSide.SELL, D("100"), 1)

    assert buy.total > D("1")
    assert sell.total > D("1")
    assert buy.schedule_version == "test-config"
    assert sell.schedule_version == "test-config"
