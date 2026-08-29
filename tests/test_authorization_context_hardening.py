import pytest

from iceberg.domain.enums import Permission
from iceberg.exceptions import PermissionDeniedError
from iceberg.risk.emergency import EmergencyStop
from iceberg.risk.permissions import PermissionManager
from iceberg.security.auth import Actor, ActorRole, AuthorizationContext, TrustedContextIssuer, ai_context

from tests.conftest import authenticated_reconciler_context


def test_manual_admin_actor_does_not_authenticate():
    context = AuthorizationContext(Actor.admin("forged-admin"), authenticated=True)

    assert context.authenticated is False
    assert not context.has(Permission.CAPITAL_ADMIN)
    with pytest.raises(PermissionDeniedError):
        context.require(Permission.CAPITAL_ADMIN)


def test_manual_authorization_context_cannot_gain_admin():
    actor = Actor("strategy-admin", ActorRole.ADMIN, frozenset(set(Permission)))
    context = AuthorizationContext(actor, authenticated=True)
    permissions = PermissionManager.from_context(context)

    assert context.authenticated is False
    assert not context.has(Permission.CAPITAL_ADMIN)
    assert not permissions.has(Permission.CAPITAL_ADMIN)


def test_ai_cannot_issue_privileged_context():
    context = ai_context()

    assert not context.has(Permission.CAPITAL_ADMIN)
    assert not hasattr(context, "issue_admin")
    with pytest.raises(PermissionDeniedError):
        TrustedContextIssuer(object())


def test_external_reconciler_cannot_disable_emergency_stop():
    emergency_stop = EmergencyStop(active=True)

    with pytest.raises(PermissionDeniedError):
        emergency_stop.deactivate(authenticated_reconciler_context())

    assert emergency_stop.active is True


def test_external_reconciler_cannot_reset_loss_counter(safe_context):
    safe_context.guard.state.consecutive_losses = 2

    with pytest.raises(PermissionDeniedError):
        safe_context.guard.reset_consecutive_losses(authenticated_reconciler_context())

    assert safe_context.guard.state.consecutive_losses == 2
