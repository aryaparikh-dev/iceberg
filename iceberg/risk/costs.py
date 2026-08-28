from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from iceberg.domain.enums import TradeSide
from iceberg.domain.models import CostBreakdown, money
from iceberg.exceptions import FailClosedError


class TransactionCostModel(ABC):
    @abstractmethod
    def estimate(self, side: TradeSide, price: Decimal, quantity: int) -> CostBreakdown:
        raise NotImplementedError

    def net_sale_proceeds(self, price: Decimal, quantity: int) -> Decimal:
        gross = money(price) * quantity
        return gross - self.estimate(TradeSide.SELL, price, quantity).total


@dataclass
class FixedTransactionCostModel(TransactionCostModel):
    buy_cost: Decimal = money("0")
    sell_cost: Decimal = money("0")
    schedule_version: str = "fixed-test"

    def __post_init__(self) -> None:
        self.buy_cost = money(self.buy_cost)
        self.sell_cost = money(self.sell_cost)

    def estimate(self, side: TradeSide, price: Decimal, quantity: int) -> CostBreakdown:
        if quantity <= 0:
            return CostBreakdown(schedule_version=self.schedule_version)
        cost = self.buy_cost if side is TradeSide.BUY else self.sell_cost
        return CostBreakdown(other=cost, schedule_version=self.schedule_version)


@dataclass
class NSEIntradayCharges:
    brokerage_flat: Decimal
    stt_sell_rate: Decimal
    exchange_txn_rate: Decimal
    sebi_rate: Decimal
    stamp_duty_buy_rate: Decimal
    gst_rate: Decimal
    schedule_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "brokerage_flat",
            "stt_sell_rate",
            "exchange_txn_rate",
            "sebi_rate",
            "stamp_duty_buy_rate",
            "gst_rate",
        ):
            setattr(self, field_name, money(getattr(self, field_name)))
        if not self.schedule_version:
            raise FailClosedError("transaction charge schedule version is required")


class NSEIntradayCostModel(TransactionCostModel):
    """Configurable Indian-equity intraday cost model.

    This intentionally requires an explicit charge schedule so statutory and
    broker charges can be reviewed when rules change.
    """

    def __init__(self, charges: NSEIntradayCharges) -> None:
        self.charges = charges

    def estimate(self, side: TradeSide, price: Decimal, quantity: int) -> CostBreakdown:
        if quantity <= 0:
            return CostBreakdown(schedule_version=self.charges.schedule_version)
        gross = money(price) * quantity
        brokerage = self.charges.brokerage_flat
        exchange = gross * self.charges.exchange_txn_rate
        sebi = gross * self.charges.sebi_rate
        stamp = gross * self.charges.stamp_duty_buy_rate if side is TradeSide.BUY else money("0")
        stt = gross * self.charges.stt_sell_rate if side is TradeSide.SELL else money("0")
        gst = (brokerage + exchange) * self.charges.gst_rate
        taxes = sebi + stt + gst
        return CostBreakdown(
            brokerage=brokerage,
            exchange_fees=exchange,
            taxes=taxes,
            stamp_duty=stamp,
            schedule_version=self.charges.schedule_version,
        )
