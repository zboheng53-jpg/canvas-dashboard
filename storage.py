"""Small JSON storage helpers for user data files."""
import copy
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_locks_guard = threading.Lock()
_path_locks: dict[str, threading.RLock] = {}
logger = logging.getLogger(__name__)


class JsonFileCorruptionError(RuntimeError):
    """Raised when a runtime JSON file cannot be decoded safely."""

    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"Malformed JSON data file: {self.path}")


def _copy_default(default):
    return copy.deepcopy(default)


def _lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(path))
    with _locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_locks[key] = lock
        return lock


def read_json_file(path: Path, default):
    path = Path(path)
    if not path.exists():
        return _copy_default(default)
    with _lock_for(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            timestamp = modified_at.strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(f"{path.name}.corrupt-{timestamp}")
            if not backup.exists():
                shutil.copy2(path, backup)
            logger.error("Malformed JSON file preserved at %s", backup)
            raise JsonFileCorruptionError(path) from error


def write_json_file(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with _lock_for(path):
        path.write_text(payload, encoding="utf-8")


def write_bytes_file(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(path):
        path.write_bytes(data)


def load_or_create_bytes(path: Path, create_value):
    path = Path(path)
    with _lock_for(path):
        if path.exists():
            return path.read_bytes()
        value = create_value()
        write_bytes_file(path, value)
        return value


def locked_json_update(path: Path, default, update_fn):
    path = Path(path)
    with _lock_for(path):
        data = read_json_file(path, default)
        updated = update_fn(data)
        if updated is None:
            updated = data
        write_json_file(path, updated)
        return updated
