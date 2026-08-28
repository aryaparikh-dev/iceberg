from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from iceberg.domain.enums import MarketRegime
from iceberg.domain.models import Candle, TradeProposal


class Strategy(ABC):
    name = "strategy"
    methodology = "rules"

    @abstractmethod
    def generate(
        self,
        symbol: str,
        history: tuple[Candle, ...],
        now: datetime,
        regime: MarketRegime,
    ) -> list[TradeProposal]:
        raise NotImplementedError
