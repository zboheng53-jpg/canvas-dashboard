"""One bounded HTTP budget for all accounts and platforms (one Web process)."""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import auth
import settings
from runtime_metrics import event
from storage import write_json_file
from user_paths import DATA_DIR

logger = logging.getLogger(__name__)
HTTP_SYNC_MAX_WORKERS = settings.HTTP_SYNC_MAX_WORKERS
HTTP_SYNC_MAX_JOBS = settings.HTTP_SYNC_MAX_JOBS
_executor = ThreadPoolExecutor(max_workers=HTTP_SYNC_MAX_WORKERS, thread_name_prefix="http-sync")
_lock = threading.Lock()
_active_jobs = {}
_platforms = {}


def get_account_identity(username):
    return auth.session_identity(username)


def is_refreshing(username, platform, job_type="refresh"):
    with _lock:
        return (username, platform, job_type) in _active_jobs


def is_any_refreshing(username):
    with _lock:
        return any(key[0] == username for key in _active_jobs)


def snapshot():
    with _lock:
        now = time.monotonic()
        return {
            "max_workers": HTTP_SYNC_MAX_WORKERS, "max_jobs": HTTP_SYNC_MAX_JOBS,
            "queued": sum(job["state"] == "queued" for job in _active_jobs.values()),
            "running": sum(job["state"] == "running" for job in _active_jobs.values()),
            "oldest_job_seconds": round(max((now - job["at"] for job in _active_jobs.values()), default=0), 3),
            "platforms": {platform: dict(stats) | {
                state: sum(key[1] == platform and job["state"] == state for key, job in _active_jobs.items())
                for state in ("queued", "running")
            } for platform, stats in _platforms.items()},
        }


def _record_snapshot():
    # The independent monitor can inspect this without importing a Web executor.
    try:
        write_json_file(DATA_DIR / "runtime_sync_snapshot.json", {"at": time.time(), **snapshot()})
    except OSError:
        logger.warning("Could not save HTTP queue metrics")


def submit_http_sync(username, platform, sync_fn, is_connected_fn=None, *,
                     job_type="refresh", write_check=None, system=False, on_finished=None):
    if not system:
        auth.check_operation_identity(username)
    identity = None if system else get_account_identity(username)
    if not system:
        auth.check_operation_identity(username)
    if identity is None and not system:
        return False
    key = (username, platform, job_type)
    job = {"state": "queued", "at": time.monotonic()}
    with _lock:
        if key in _active_jobs or len(_active_jobs) >= HTTP_SYNC_MAX_JOBS:
            return False
        _active_jobs[key] = job
        _platforms.setdefault(platform, {"success": 0, "failed": 0, "cancelled": 0,
                                        "duration_seconds": None, "last_success_at": None})
    event("sync", platform=platform, job_type=job_type, state="queued")
    _record_snapshot()

    def worker():
        started = time.monotonic()
        state = "cancelled"
        try:
            with auth.identity_scope(username, identity, write_check):
                if not system:
                    auth.check_operation_identity(username)
                if is_connected_fn and not is_connected_fn(username):
                    return
                if write_check and not write_check():
                    return
                with _lock:
                    job["state"] = "running"
                event("sync", platform=platform, job_type=job_type, state="running",
                      queue_seconds=round(started - job["at"], 3))
                _record_snapshot()
                result = sync_fn()
                state = "failed" if isinstance(result, dict) and (
                    result.get("ok") is False or result.get("sync_complete") is False
                    or result.get("stale") or result.get("cached")
                ) else "success"
        except auth.AccountIdentityChanged:
            state = "cancelled"
        except Exception as exc:
            state = "failed"
            logger.warning("HTTP sync failed: platform=%s error_type=%s", platform, type(exc).__name__)
        finally:
            if on_finished:
                try:
                    on_finished()
                except Exception as exc:
                    logger.warning("HTTP completion callback failed: platform=%s error_type=%s", platform, type(exc).__name__)
            duration = round(time.monotonic() - started, 3)
            with _lock:
                stats = _platforms[platform]
                stats[state] += 1
                stats["duration_seconds"] = duration
                if state == "success":
                    stats["last_success_at"] = time.time()
                if _active_jobs.get(key) is job:
                    _active_jobs.pop(key, None)
            event("sync", platform=platform, job_type=job_type, state=state, duration_seconds=duration)
            _record_snapshot()
    try:
        _executor.submit(worker)
    except Exception:
        with _lock:
            _active_jobs.pop(key, None)
        raise
    return True
