"""Non-sensitive, per-user platform connection and synchronization metadata."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import settings
from storage import locked_json_update, read_json_file
from user_paths import user_dir

PLATFORMS = ("canvas", "haoke", "zhixuemeng", "zhihuishu")
CONNECTION_STATES = {"unconfigured", "connected", "disconnected", "needs_reauth"}
DATA_STATES = {"unavailable", "fresh", "cached", "stale"}
CST = timezone(timedelta(hours=8))


def _path(username: str) -> Path:
    return user_dir(username) / "platform_sync_status.json"


def _now() -> str:
    return datetime.now(CST).isoformat()


def _default_platform() -> dict:
    return {
        "connection_state": "unconfigured",
        "data_state": "unavailable",
        "connected_at": None,
        "disconnected_at": None,
        "last_attempt_at": None,
        "last_success_at": None,
        "consecutive_failures": 0,
        "error_code": None,
        "error_message": None,
        "calendar_eligible": False,
    }


def _normalize_platform(value: dict | None) -> dict:
    result = _default_platform()
    if isinstance(value, dict):
        result.update({key: value.get(key) for key in result if key in value})
    if result["connection_state"] not in CONNECTION_STATES:
        result["connection_state"] = "unconfigured"
    if result["data_state"] not in DATA_STATES:
        result["data_state"] = "unavailable"
    if not isinstance(result["consecutive_failures"], int) or result["consecutive_failures"] < 0:
        result["consecutive_failures"] = 0
    result["calendar_eligible"] = bool(result["calendar_eligible"])
    return result


def load(username: str) -> dict:
    raw = read_json_file(_path(username), {"version": 1, "platforms": {}})
    platforms = raw.get("platforms", {}) if isinstance(raw, dict) else {}
    return {
        "version": 1,
        "platforms": {platform: _normalize_platform(platforms.get(platform)) for platform in PLATFORMS},
    }


def get(username: str, platform: str) -> dict:
    if platform not in PLATFORMS:
        raise ValueError("unsupported platform")
    return load(username)["platforms"][platform]


def update(username: str, platform: str, mutate) -> dict:
    if platform not in PLATFORMS:
        raise ValueError("unsupported platform")

    def apply(raw):
        data = raw if isinstance(raw, dict) else {}
        data["version"] = 1
        platforms = data.setdefault("platforms", {})
        value = _normalize_platform(platforms.get(platform))
        updated = mutate(value) or value
        platforms[platform] = _normalize_platform(updated)
        return data

    return locked_json_update(_path(username), {"version": 1, "platforms": {}}, apply)["platforms"][platform]


def mark_connected(username: str, platform: str) -> dict:
    def apply(value):
        if value["connection_state"] != "connected":
            value["connected_at"] = _now()
        value["connection_state"] = "connected"
        value["disconnected_at"] = None
        value["calendar_eligible"] = False
        value["error_code"] = None
        value["error_message"] = None
        return value
    return update(username, platform, apply)


def mark_disconnected(username: str, platform: str, has_cache: bool) -> dict:
    def apply(value):
        value["connection_state"] = "disconnected"
        value["disconnected_at"] = _now()
        value["data_state"] = "cached" if has_cache else "unavailable"
        value["calendar_eligible"] = False
        value["error_code"] = None
        value["error_message"] = None
        return value
    return update(username, platform, apply)


def mark_unconfigured(username: str, platform: str) -> dict:
    def apply(value):
        value.update(_default_platform())
        return value
    return update(username, platform, apply)


def record_result(username: str, platform: str, *, ok: bool, has_cache: bool,
                  cached: bool = False, error_code: str | None = None,
                  error_message: str | None = None, needs_reauth: bool = False) -> dict:
    """Record a real upstream attempt, never a cache-only read."""
    def apply(value):
        value["last_attempt_at"] = _now()
        if needs_reauth:
            value["connection_state"] = "needs_reauth"
        if ok and not cached:
            value["connection_state"] = "connected"
            value["last_success_at"] = _now()
            value["data_state"] = "fresh"
            value["consecutive_failures"] = 0
            value["error_code"] = None
            value["error_message"] = None
            value["calendar_eligible"] = True
        elif not ok:
            value["consecutive_failures"] += 1
            value["data_state"] = "cached" if has_cache else "unavailable"
            value["error_code"] = error_code or "sync_failed"
            value["error_message"] = (error_message or "同步失败")[:240]
        return value
    return update(username, platform, apply)


def response_sync(username: str, platform: str, *, connection_state: str | None = None,
                  has_cache: bool = False, refreshing: bool = False) -> dict:
    """Return a compatible public status, lazily inferring old account state."""
    status = get(username, platform)
    if status["connection_state"] == "unconfigured" and connection_state in CONNECTION_STATES:
        status["connection_state"] = connection_state
        status["data_state"] = "cached" if has_cache else status["data_state"]
    if status["connection_state"] == "disconnected":
        status["data_state"] = "cached" if has_cache else "unavailable"
    elif has_cache and status["data_state"] == "unavailable":
        status["data_state"] = "cached"
    return {key: status[key] for key in (
        "connection_state", "data_state", "last_attempt_at", "last_success_at",
        "consecutive_failures", "error_code", "error_message",
    )} | {"refreshing": bool(refreshing)}


def is_calendar_eligible(username: str, platform: str, *, legacy_default: bool = False) -> bool:
    """Use a safe compatibility default until an old account has metadata."""
    if not _path(username).exists():
        return legacy_default
    return bool(get(username, platform)["calendar_eligible"])


def warning_seconds(platform: str) -> int:
    if platform == "zhihuishu":
        return settings.ZHIHUISHU_SYNC_WARNING_SECONDS
    return settings.PLATFORM_SYNC_WARNING_SECONDS
