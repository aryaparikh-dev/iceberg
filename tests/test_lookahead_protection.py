from iceberg.backtesting.engine import BacktestEngine
from iceberg.market.calendar import StaticBacktestCalendar
from iceberg.risk.costs import FixedTransactionCostModel
from iceberg.risk.slippage import FixedBpsSlippageModel
from iceberg.domain.models import Candle, TradeProposal
from iceberg.strategies.base import Strategy

from tests.conftest import D, ist_datetime


class RecordingStrategy(Strategy):
    name = "recording"

    def __init__(self):
        self.history_lengths = []

    def generate(self, symbol, history, now, regime):
        self.history_lengths.append(len(history))
        return [TradeProposal.hold(symbol, price=history[-1].close, decision_id=f"hold-{len(history)}")]


def test_backtest_only_passes_history_available_at_decision_time(settings):
    candles = [
        Candle("ABC", ist_datetime(10, 0), D("10"), D("10"), D("10"), D("10"), D("1000")),
        Candle("ABC", ist_datetime(10, 1), D("11"), D("11"), D("11"), D("11"), D("1000")),
        Candle("ABC", ist_datetime(10, 2), D("12"), D("12"), D("12"), D("12"), D("1000")),
    ]
    strategy = RecordingStrategy()

    BacktestEngine(
        settings=settings,
        cost_model=FixedTransactionCostModel(),
        slippage_model=FixedBpsSlippageModel(D("0")),
        calendar=StaticBacktestCalendar(trading_days={ist_datetime(10, 0).date()}),
    ).run({"ABC": candles}, strategy)

    assert strategy.history_lengths == [1, 2, 3]
