import threading

import pytest

from maintenance import maintenance_lock


def test_account_maintenance_is_serialized_and_wait_is_bounded(tmp_path):
    data = tmp_path / "data"
    entered = threading.Event()
    release = threading.Event()

    def account_delete():
        with maintenance_lock(data):
            entered.set()
            assert release.wait(5)

    worker = threading.Thread(target=account_delete)
    worker.start()
    try:
        assert entered.wait(5)
        assert (tmp_path / ".maintenance.lock").exists()
        with pytest.raises(TimeoutError, match="maintenance"):
            with maintenance_lock(data, timeout=0.05):
                pytest.fail("Concurrent maintenance must not enter")
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    with maintenance_lock(data, timeout=0.05):
        pass


def test_maintenance_target_can_follow_deployment_root_for_external_data_volume(tmp_path, monkeypatch):
    target = tmp_path / "deployment" / "maintenance"
    monkeypatch.setenv("CANVAS_DASHBOARD_MAINTENANCE_TARGET", str(target))
    with maintenance_lock(tmp_path / "separate-volume" / "data"):
        assert (target.parent / ".maintenance.lock").exists()
        assert not (tmp_path / "separate-volume" / ".maintenance.lock").exists()
