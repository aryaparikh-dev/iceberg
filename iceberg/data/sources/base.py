from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from iceberg.data.models import CorporateAction, HistoricalBar, InstrumentMetadata
from iceberg.market.calendar import TradingCalendar


class HistoricalMarketDataSource(ABC):
    """Provider-neutral historical-data boundary.

    Network/commercial providers should be added as adapters behind this
    interface. The core backtester consumes normalized local records only.
    """

    source_id: str

    @abstractmethod
    def get_symbols(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_candles(
        self,
        symbols: list[str] | None = None,
        *,
        start: date | None = None,
        end: date | None = None,
        interval: str | None = None,
    ) -> list[HistoricalBar]:
        raise NotImplementedError

    @abstractmethod
    def get_trading_calendar(self) -> TradingCalendar:
        raise NotImplementedError

    @abstractmethod
    def get_instrument_metadata(self, symbols: list[str] | None = None) -> dict[str, InstrumentMetadata]:
        raise NotImplementedError

    @abstractmethod
    def get_corporate_actions(self, symbols: list[str] | None = None) -> list[CorporateAction]:
        raise NotImplementedError
