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
_proc_lock_counts: dict[str, int] = {}
_proc_lock_files: dict[str, any] = {}
logger = logging.getLogger(__name__)

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import fcntl
except ImportError:
    fcntl = None


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


class _InterprocessLockContext:
    def __init__(self, path: Path, timeout: float = 30.0):
        self.path = Path(path)
        self.key = os.path.normcase(os.path.abspath(path))
        self.timeout = timeout
        self.lock_path = self.path.parent / f".{self.path.name}.lock"

    def __enter__(self):
        with _locks_guard:
            current_count = _proc_lock_counts.get(self.key, 0)
            if current_count > 0:
                _proc_lock_counts[self.key] = current_count + 1
                return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.lock_path, "a+b")
        fileno = f.fileno()
        start = time.time()
        while True:
            try:
                if msvcrt:
                    f.seek(0)
                    msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
                    break
                elif fcntl:
                    fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                else:
                    break
            except (BlockingIOError, PermissionError, OSError):
                if time.time() - start >= self.timeout:
                    try:
                        f.close()
                    except OSError:
                        pass
                    raise TimeoutError(f"Timed out waiting for file lock on {self.path}")
                time.sleep(0.02)

        with _locks_guard:
            _proc_lock_counts[self.key] = 1
            _proc_lock_files[self.key] = f
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with _locks_guard:
            count = _proc_lock_counts.get(self.key, 0)
            if count > 1:
                _proc_lock_counts[self.key] = count - 1
                return
            _proc_lock_counts.pop(self.key, None)
            f = _proc_lock_files.pop(self.key, None)

        if f is not None:
            try:
                if msvcrt:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                f.close()
            except Exception:
                pass


def interprocess_lock(path: Path, timeout: float = 30.0):
    """Context manager for cross-process file locking."""
    return _InterprocessLockContext(path, timeout=timeout)


def _atomic_replace(src: Path, dst: Path) -> None:
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            os.replace(src, dst)
            return
        except (PermissionError, OSError):
            if attempt == max_attempts - 1:
                raise
            time.sleep(0.02 * (attempt + 1))


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_file_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_file_str)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        _atomic_replace(temp_path, path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise


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
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    with _lock_for(path):
        _atomic_write_bytes(path, payload)


def write_bytes_file(path: Path, data: bytes) -> None:
    path = Path(path)
    with _lock_for(path):
        _atomic_write_bytes(path, data)


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
        with interprocess_lock(path):
            data = read_json_file(path, default)
            updated = update_fn(data)
            if updated is None:
                updated = data
            write_json_file(path, updated)
            return updated

