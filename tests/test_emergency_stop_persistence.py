import pytest

from iceberg.exceptions import PermissionDeniedError
from iceberg.persistence.repositories import SQLiteStateStore
from iceberg.risk.emergency import EmergencyStop
from iceberg.security.auth import ai_context


def test_emergency_stop_survives_restart(tmp_path):
    store = SQLiteStateStore(tmp_path / "stop.sqlite3")
    stop = EmergencyStop(active=False, store=store)
    stop.activate()

    restarted = EmergencyStop.load(store)

    assert restarted.active is True


def test_ai_cannot_disable_emergency_stop(tmp_path):
    store = SQLiteStateStore(tmp_path / "stop-ai.sqlite3")
    stop = EmergencyStop(active=True, store=store)

    with pytest.raises(PermissionDeniedError):
        stop.deactivate(ai_context())
