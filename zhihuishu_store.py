"""Per-user Zhihuishu worker status, cache, and item state storage."""
import time
from pathlib import Path

import settings
from platform_state import PlatformStateStore
from storage import locked_json_update, read_json_file, write_json_file

from user_paths import DATA_DIR

STATUS_DEFAULT = {
    "session": "not_logged_in",
    "worker": "unknown",
    "last_keepalive_at": None,
    "last_fetch_at": None,
    "last_success_at": None,
    "last_error": "",
}

STATE_DEFAULT = {"hidden": [], "highlighted": [], "deleted": []}


def _user_dir(username: str) -> Path:
    import auth
    if auth.DATA_DIR.resolve() == DATA_DIR.resolve() and auth.account_deletion_in_progress(username):
        raise RuntimeError('account deletion in progress')
    d = DATA_DIR / "users" / username
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path, default):
    return read_json_file(path, default)


def _write_json(path: Path, data):
    write_json_file(path, data)


def _status_file(username: str) -> Path:
    return _user_dir(username) / "zhihuishu_status.json"


def _cache_file(username: str) -> Path:
    return _user_dir(username) / "zhihuishu_cache.json"


def _state_file(username: str) -> Path:
    return _user_dir(username) / "zhihuishu_state.json"


_state_store = PlatformStateStore(_state_file, str)


def load_status(username: str) -> dict:
    status = STATUS_DEFAULT.copy()
    status.update(_read_json(_status_file(username), {}))
    return status


def save_status(username: str, updates: dict) -> dict:
    def update(current):
        status = {**STATUS_DEFAULT, **current}
        if 'session' in updates and updates['session'] != status.get('session'):
            status['connection_revision'] = int(status.get('connection_revision', 0)) + 1
        status.update(updates)
        return status
    return locked_json_update(_status_file(username), {}, update)


def save_cache(username: str, items: list[dict], fetched_at: float | None = None) -> dict:
    cache = {"items": items, "fetched_at": fetched_at or time.time()}
    _write_json(_cache_file(username), cache)
    return cache


def load_cache(username: str, stale_after_seconds: int = settings.ZHIHUISHU_CACHE_STALE_SECONDS) -> dict:
    cache = _read_json(_cache_file(username), {"items": [], "fetched_at": None})
    fetched_at = cache.get("fetched_at")
    stale = True
    if fetched_at is not None:
        stale = (time.time() - float(fetched_at)) > stale_after_seconds
    return {
        "items": cache.get("items", []),
        "fetched_at": fetched_at,
        "stale": stale,
    }


def load_state(username: str) -> dict:
    return _state_store.load(username)


def save_state(username: str, state: dict) -> dict:
    return _state_store.save(username, state)


def update_state(username: str, action: str, item_id) -> dict:
    return _state_store.update(username, action, item_id)


def update_override(username: str, item_id, patch=None, restore=False) -> dict:
    return _state_store.update_override(username, item_id, patch, restore)
