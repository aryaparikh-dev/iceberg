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
    def user(cls, actor_id: str = "user") -> "Actor":
        return cls(
            actor_id=actor_id,
            role=ActorRole.USER,
            permissions=frozenset({Permission.FUNDING_REQUEST}),
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
            permissions=frozenset({Permission.FUNDING_CONFIRM}),
        )


_AUTH_CONTEXT_ISSUER_TOKEN = object()


@dataclass(frozen=True)
class AuthorizationContext:
    actor: Actor
    authenticated: bool = False
    _issuer_token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer_token is not _AUTH_CONTEXT_ISSUER_TOKEN:
            object.__setattr__(self, "authenticated", False)

    def has(self, permission: Permission) -> bool:
        return self.authenticated and permission in self.actor.permissions

    def require(self, permission: Permission) -> None:
        if not self.has(permission):
            raise PermissionDeniedError(f"{self.actor.actor_id} lacks {permission.value}")


class TrustedContextIssuer:
    """Issues authenticated contexts after an external authentication step.

    This reduces accidental privilege forging in normal code, but same-process
    Python is not a security sandbox. Future live trading must isolate this
    issuer outside strategy-controlled code and enforce permissions broker-side.
    """

    def __init__(self, issuer_token: object) -> None:
        if issuer_token is not _AUTH_CONTEXT_ISSUER_TOKEN:
            raise PermissionDeniedError("trusted context issuer cannot be constructed by ordinary code")
        self._issuer_token = issuer_token

    def issue_ai(self, actor_id: str = "ai") -> AuthorizationContext:
        return self._issue(Actor.ai(actor_id))

    def issue_user(self, actor_id: str = "user") -> AuthorizationContext:
        return self._issue(Actor.user(actor_id))

    def issue_admin(self, actor_id: str = "admin") -> AuthorizationContext:
        return self._issue(Actor.admin(actor_id))

    def issue_external_reconciler(self, actor_id: str = "external-reconciler") -> AuthorizationContext:
        return self._issue(Actor.external_reconciler(actor_id))

    def _issue(self, actor: Actor) -> AuthorizationContext:
        return AuthorizationContext(actor=actor, authenticated=True, _issuer_token=self._issuer_token)


_TRUSTED_CONTEXT_ISSUER = TrustedContextIssuer(_AUTH_CONTEXT_ISSUER_TOKEN)


def ai_context() -> AuthorizationContext:
    return _TRUSTED_CONTEXT_ISSUER.issue_ai()


def _trusted_context_issuer() -> TrustedContextIssuer:
    return _TRUSTED_CONTEXT_ISSUER
