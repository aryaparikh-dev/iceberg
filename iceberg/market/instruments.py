from __future__ import annotations

from dataclasses import dataclass

from iceberg.domain.enums import AssetClass


@dataclass(frozen=True)
class InstrumentMetadata:
    symbol: str
    asset_class: AssetClass
    exchange: str
    sector: str | None = None
    series: str | None = None
    liquidity_classification: str | None = None
    tradable: bool = True


class InstrumentMetadataProvider:
    def get(self, symbol: str) -> InstrumentMetadata | None:
        return None


@dataclass(frozen=True)
class SectorConcentrationPolicy:
    max_fraction_per_sector: float | None = None
    require_sector_data: bool = False
