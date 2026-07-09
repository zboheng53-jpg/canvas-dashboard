"""Small JSON storage helpers for user data files."""
import copy
import json
import os
import tempfile
import threading
import time
from pathlib import Path

_locks_guard = threading.Lock()
_path_locks: dict[str, threading.RLock] = {}


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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _copy_default(default)


def write_json_file(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(20):
            try:
                os.replace(tmp_name, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def locked_json_update(path: Path, default, update_fn):
    path = Path(path)
    with _lock_for(path):
        data = read_json_file(path, default)
        updated = update_fn(data)
        if updated is None:
            updated = data
        write_json_file(path, updated)
        return updated
