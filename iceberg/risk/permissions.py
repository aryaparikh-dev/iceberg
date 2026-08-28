from __future__ import annotations

from dataclasses import dataclass, field

from iceberg.domain.enums import Permission
from iceberg.exceptions import PermissionDeniedError


@dataclass
class PermissionManager:
    permissions: set[Permission] = field(default_factory=set)
    actor: str = "AI"

    @classmethod
    def default_ai(cls) -> "PermissionManager":
        return cls(
            permissions={
                Permission.MARKET_DATA_READ,
                Permission.PORTFOLIO_READ,
                Permission.PAPER_TRADE,
            },
            actor="AI",
        )

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        if not self.has(permission):
            raise PermissionDeniedError(f"missing permission {permission.value}")

    def grant(self, permission: Permission, *, actor: str) -> None:
        if self.actor == "AI":
            raise PermissionDeniedError("strategies and AI cannot modify their own permissions")
        if actor.upper() != "ADMIN":
            raise PermissionDeniedError("only ADMIN can grant permissions")
        self.permissions.add(permission)

    def revoke(self, permission: Permission) -> None:
        self.permissions.discard(permission)
