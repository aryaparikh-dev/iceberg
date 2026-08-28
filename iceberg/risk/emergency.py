from __future__ import annotations

from dataclasses import dataclass

from iceberg.domain.enums import Permission, TradeSide
from iceberg.security.auth import AuthorizationContext


@dataclass
class EmergencyStop:
    active: bool = False
    allow_position_exits: bool = True
    store: object | None = None

    def __post_init__(self) -> None:
        if self.store is not None:
            saved = self.store.load_emergency_stop()
            if saved is not None:
                self.active, self.allow_position_exits = saved
            else:
                self.persist()

    @classmethod
    def load(cls, store) -> "EmergencyStop":
        return cls(store=store)

    def blocks(self, side: TradeSide) -> bool:
        if not self.active:
            return False
        if side is TradeSide.SELL and self.allow_position_exits:
            return False
        return True

    def activate(self) -> None:
        self.active = True
        self.persist()

    def deactivate(self, context: AuthorizationContext) -> None:
        context.require(Permission.CAPITAL_ADMIN)
        self.active = False
        self.persist()

    def persist(self) -> None:
        if self.store is not None:
            self.store.save_emergency_stop(active=self.active, allow_position_exits=self.allow_position_exits)
