"""Coordinate local account mutations with production backup/release scripts."""
from contextlib import contextmanager
from pathlib import Path
import os
import threading

from storage import interprocess_lock

_guard = threading.RLock()


@contextmanager
def maintenance_lock(data_dir: Path, timeout: float = 30.0):
    # storage's lock for a target named 'maintenance' is .maintenance.lock,
    # exactly the file used by flock in deploy/*.sh.
    override = os.environ.get("CANVAS_DASHBOARD_MAINTENANCE_TARGET")
    target = Path(override) if override else Path(data_dir).resolve().parent / "maintenance"
    if not _guard.acquire(timeout=timeout):
        raise TimeoutError("Timed out waiting for maintenance lock")
    try:
        with interprocess_lock(target, timeout=timeout):
            yield
    finally:
        _guard.release()
