from __future__ import annotations

from dataclasses import dataclass

from iceberg.domain.enums import TradeSide


@dataclass
class EmergencyStop:
    active: bool = False
    allow_position_exits: bool = True

    def blocks(self, side: TradeSide) -> bool:
        if not self.active:
            return False
        if side is TradeSide.SELL and self.allow_position_exits:
            return False
        return True
