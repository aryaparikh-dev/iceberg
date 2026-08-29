from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from iceberg.data.models import InstrumentMetadata


@dataclass(frozen=True)
class UniverseSelection:
    name: str
    as_of: date
    symbols: tuple[str, ...]
    survivorship_bias_risk: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


class StaticUniverse:
    def __init__(self, name: str, symbols: list[str] | tuple[str, ...], *, survivorship_bias_risk: bool = True) -> None:
        self.name = name
        self.symbols = tuple(sorted({symbol.upper() for symbol in symbols}))
        self.survivorship_bias_risk = survivorship_bias_risk

    def eligible_symbols(self, as_of: date, metadata: dict[str, InstrumentMetadata] | None = None) -> UniverseSelection:
        metadata = metadata or {}
        eligible = tuple(symbol for symbol in self.symbols if metadata.get(symbol, InstrumentMetadata(symbol)).is_tradable_on(as_of))
        warnings = ("SURVIVORSHIP_BIAS_RISK=TRUE",) if self.survivorship_bias_risk else ()
        return UniverseSelection(self.name, as_of, eligible, self.survivorship_bias_risk, warnings)


class PointInTimeUniverse:
    def __init__(self, name: str, membership_by_date: dict[date, list[str] | tuple[str, ...]]) -> None:
        if not membership_by_date:
            raise ValueError("point-in-time universe requires membership history")
        self.name = name
        self.membership_by_date = {
            as_of: tuple(sorted({symbol.upper() for symbol in symbols}))
            for as_of, symbols in membership_by_date.items()
        }

    def eligible_symbols(self, as_of: date, metadata: dict[str, InstrumentMetadata] | None = None) -> UniverseSelection:
        metadata = metadata or {}
        effective_dates = [membership_date for membership_date in self.membership_by_date if membership_date <= as_of]
        if not effective_dates:
            return UniverseSelection(self.name, as_of, tuple(), False, ("NO_POINT_IN_TIME_MEMBERSHIP",))
        effective = max(effective_dates)
        symbols = self.membership_by_date[effective]
        eligible = tuple(symbol for symbol in symbols if metadata.get(symbol, InstrumentMetadata(symbol)).is_tradable_on(as_of))
        return UniverseSelection(self.name, as_of, eligible, False, tuple())
