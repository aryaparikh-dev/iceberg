from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from iceberg.domain.enums import Permission
from iceberg.exceptions import PermissionDeniedError


class ActorRole(str, Enum):
    AI = "AI"
    USER = "USER"
    ADMIN = "ADMIN"
    EXTERNAL_RECONCILER = "EXTERNAL_RECONCILER"
    RISK_OFFICER = "RISK_OFFICER"


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: ActorRole
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    @classmethod
    def ai(cls, actor_id: str = "ai") -> "Actor":
        return cls(
            actor_id=actor_id,
            role=ActorRole.AI,
            permissions=frozenset(
                {
                    Permission.MARKET_DATA_READ,
                    Permission.PORTFOLIO_READ,
                    Permission.PAPER_TRADE,
                }
            ),
        )

    @classmethod
    def admin(cls, actor_id: str = "admin") -> "Actor":
        return cls(
            actor_id=actor_id,
            role=ActorRole.ADMIN,
            permissions=frozenset(set(Permission)),
        )

    @classmethod
    def external_reconciler(cls, actor_id: str = "external-reconciler") -> "Actor":
        return cls(
            actor_id=actor_id,
            role=ActorRole.EXTERNAL_RECONCILER,
            permissions=frozenset({Permission.FUNDING_CONFIRM, Permission.CAPITAL_ADMIN}),
        )


@dataclass(frozen=True)
class AuthorizationContext:
    actor: Actor
    authenticated: bool = True

    def has(self, permission: Permission) -> bool:
        return self.authenticated and permission in self.actor.permissions

    def require(self, permission: Permission) -> None:
        if not self.has(permission):
            raise PermissionDeniedError(f"{self.actor.actor_id} lacks {permission.value}")


def ai_context() -> AuthorizationContext:
    return AuthorizationContext(Actor.ai())


def admin_context() -> AuthorizationContext:
    return AuthorizationContext(Actor.admin())


def external_reconciler_context() -> AuthorizationContext:
    return AuthorizationContext(Actor.external_reconciler())
