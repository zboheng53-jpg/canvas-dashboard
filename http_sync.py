"""Unified bounded background executor for HTTP platform synchronization."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import auth

logger = logging.getLogger(__name__)

# Bounded site-wide concurrency for background HTTP sync (initial budget: 2)
HTTP_SYNC_MAX_WORKERS = 2
HTTP_SYNC_MAX_JOBS = 32
_executor = ThreadPoolExecutor(max_workers=HTTP_SYNC_MAX_WORKERS, thread_name_prefix="http-sync")

_lock = threading.Lock()
# Mapping: (username, platform) -> active job token
_active_jobs: dict[tuple[str, str], object] = {}


def get_account_identity(username: str) -> Any:
    """Retrieve immutable account identity and version if available."""
    return auth.session_identity(username)


def is_refreshing(username: str, platform: str) -> bool:
    """Return True if a sync task for (username, platform) is queued or running."""
    with _lock:
        return (username, platform) in _active_jobs


def is_any_refreshing(username: str) -> bool:
    """Return True if any sync task for username is queued or running."""
    with _lock:
        return any(u == username for (u, _p) in _active_jobs)


def submit_http_sync(
    username: str,
    platform: str,
    sync_fn: Callable[[], Any],
    is_connected_fn: Callable[[str], bool] | None = None,
) -> bool:
    """Submit a sync task to the bounded executor.

    Deduplicates by (username, platform).
    Aborts execution and writeback if the account is recreated, deleted, or disconnected.
    Returns True if scheduled, False if already active or account inactive.
    """
    initial_identity = get_account_identity(username)
    if initial_identity is None:
        return False

    with _lock:
        key = (username, platform)
        if key in _active_jobs or len(_active_jobs) >= HTTP_SYNC_MAX_JOBS:
            return False
        job_token = object()
        _active_jobs[key] = job_token

    def _worker():
        try:
            current_identity = get_account_identity(username)
            if current_identity != initial_identity:
                logger.info(
                    "HTTP sync aborted for %s on %s: account identity changed before execution",
                    username, platform,
                )
                return

            if is_connected_fn and not is_connected_fn(username):
                logger.info(
                    "HTTP sync aborted for %s on %s: platform disconnected before execution",
                    username, platform,
                )
                return

            sync_fn()

        except Exception as exc:
            # Network exception messages can contain subscription URLs and tokens.
            logger.warning("HTTP background sync failed on %s (%s)", platform, type(exc).__name__)
        finally:
            with _lock:
                if _active_jobs.get(key) is job_token:
                    _active_jobs.pop(key, None)

    try:
        _executor.submit(_worker)
        return True
    except Exception:
        with _lock:
            if _active_jobs.get(key) is job_token:
                _active_jobs.pop(key, None)
        raise
