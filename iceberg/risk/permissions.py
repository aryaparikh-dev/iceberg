from __future__ import annotations

from dataclasses import dataclass, field

from iceberg.domain.enums import Permission
from iceberg.exceptions import PermissionDeniedError
from iceberg.security.auth import ActorRole, AuthorizationContext, ai_context


@dataclass
class PermissionManager:
    permissions: set[Permission] = field(default_factory=set)
    actor: str = "AI"
    context: AuthorizationContext | None = None

    @classmethod
    def default_ai(cls) -> "PermissionManager":
        context = ai_context()
        return cls(
            permissions={
                Permission.MARKET_DATA_READ,
                Permission.PORTFOLIO_READ,
                Permission.PAPER_TRADE,
            },
            actor="AI",
            context=context,
        )

    @classmethod
    def from_context(cls, context: AuthorizationContext) -> "PermissionManager":
        permissions = set(context.actor.permissions) if context.authenticated else set()
        return cls(permissions=permissions, actor=context.actor.role.value, context=context)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        if not self.has(permission):
            raise PermissionDeniedError(f"missing permission {permission.value}")

    def grant(self, permission: Permission, *, context: AuthorizationContext) -> None:
        if self.context is not None and self.context.actor.role is ActorRole.AI:
            raise PermissionDeniedError("strategies and AI cannot modify their own permissions")
        context.require(Permission.CAPITAL_ADMIN)
        self.permissions.add(permission)

    def revoke(self, permission: Permission) -> None:
        self.permissions.discard(permission)
