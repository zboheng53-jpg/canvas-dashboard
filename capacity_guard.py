"""Pre-launch capacity guard: the emergency brake for new registrations.

The small-group deployment runs one Web process with a bounded thread pool and
process-local file locks. Adding accounts adds background platform refreshes,
browser sessions and slow upstream calls, so *parallel* work, not the account
count alone, is what can take the server down.

This module watches three admission thresholds and closes **new registrations**
as soon as one of them is reached. Existing accounts keep working; the public
register page explains the pause instead of offering a form that would fail,
and `/api/auth/register` rejects with the same reason so the UI cannot be
bypassed by calling the API directly.

Metrics are aggregates only and never contain usernames. An unreadable metric
file is reported fail-closed: the guard keeps registrations closed instead of
assuming there is room left.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import auth
import login_capacity
import settings
import user_paths
from storage import locked_json_update, read_json_file

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

PRESENCE_FILE = ".capacity_presence.json"
STATE_FILE = ".capacity_guard_state.json"

REASON_MANUAL = "manual_pause"
REASON_TOTAL_USERS = "capacity_total_users"
REASON_ACTIVE_USERS = "capacity_active_users"
REASON_CONNECTED_PLATFORMS = "capacity_connected_platforms"
REASON_CHECK_FAILED = "capacity_check_failed"

# Admission gates in reporting order, as (reason code, metric field).
_GATES = (
    (REASON_TOTAL_USERS, "total_users"),
    (REASON_ACTIVE_USERS, "active_users"),
    (REASON_CONNECTED_PLATFORMS, "connected_platforms"),
)
_CAPACITY_REASONS = frozenset(
    {REASON_TOTAL_USERS, REASON_ACTIVE_USERS, REASON_CONNECTED_PLATFORMS}
)

_CACHE_TTL_SECONDS = 2.0
_TOUCH_MIN_INTERVAL_SECONDS = 60 * 60
_PRESENCE_RETENTION_DAYS = 90

_cache_lock = threading.Lock()
_cache = {"key": None, "at": 0.0, "value": None}
_touch_lock = threading.Lock()
_last_touch: dict[tuple[str, str], float] = {}
_latch_lock = threading.Lock()
_last_latch: dict[str, tuple] = {}


@dataclass(frozen=True)
class CapacityDecision:
    """One admission decision plus the aggregate evidence behind it."""

    registration_open: bool
    reason: str | None
    reasons: tuple[str, ...]
    metrics: dict | None
    thresholds: dict
    manual_pause: bool
    checked_at: str

    def as_dict(self) -> dict:
        return {
            "registration_open": self.registration_open,
            "reason": self.reason,
            "reasons": list(self.reasons),
            "manual_pause": self.manual_pause,
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "checked_at": self.checked_at,
        }


_CAPACITY_COPY = {
    "title": "注册暂时关闭",
    "badge": "容量已满",
    "paragraphs": (
        "感谢你关注 Canvas Dashboard。由于服务器并行处理能力有限，本站已经达到本轮小范围开放的用户上限，因此暂时停止新注册。",
        "我们正在处理扩容与并发隔离，解决后会继续开放注册；开放时间会在本页和更新日志中说明。",
    ),
    "note": "已有账号不受影响，可以正常登录并继续使用。",
    "thanks": "谢谢你的期待与谅解。",
    "summary": "服务器并行能力已达本轮开放的用户上限，暂时停止新注册；已有账号仍可正常登录。",
}

_MANUAL_COPY = {
    "title": "注册暂时关闭",
    "badge": "维护中",
    "paragraphs": (
        "站点正在维护，暂时停止新注册。",
        "维护结束后会重新开放注册；具体时间请留意本页提示或联系站点维护者。",
    ),
    "note": "已有账号不受影响，仍可正常登录。",
    "thanks": "谢谢你的理解。",
    "summary": "暂时停止新账户注册，已有账户仍可登录。",
}

_CHECK_COPY = {
    "title": "注册暂时关闭",
    "badge": "保护中",
    "paragraphs": (
        "本站暂时停止新注册。容量状态正在核对，为避免服务器过载，在确认可用容量前不会开放注册。",
        "核对完成后会恢复注册。",
    ),
    "note": "已有账号不受影响，可以正常登录并继续使用。",
    "thanks": "谢谢你的耐心与谅解。",
    "summary": "容量状态暂时无法确认，为保护服务器已暂停新注册；已有账号仍可正常登录。",
}


def data_root() -> Path:
    """Resolve the active data root per call so tests and previews can redirect it."""
    return Path(user_paths.DATA_DIR)


def _now() -> datetime:
    return datetime.now(CST)


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CST)
    return parsed


def thresholds() -> dict:
    return {
        "total_users": settings.CAPACITY_MAX_TOTAL_USERS,
        "active_users": settings.CAPACITY_MAX_ACTIVE_USERS,
        "connected_platforms": settings.CAPACITY_MAX_CONNECTED_PLATFORMS,
    }


def _presence(root: Path) -> dict:
    data = read_json_file(root / PRESENCE_FILE, {})
    seen = data.get("seen", {}) if isinstance(data, dict) else {}
    return seen if isinstance(seen, dict) else {}


def _latest_activity(record: dict, seen_at) -> datetime | None:
    known = [
        parsed
        for parsed in (_parse_time(record.get("last_login_at")), _parse_time(seen_at))
        if parsed is not None
    ]
    return max(known) if known else None


def _connected_platforms(root: Path) -> int:
    users_dir = root / "users"
    if not users_dir.is_dir():
        return 0
    total = 0
    for path in sorted(users_dir.glob("*/platform_sync_status.json")):
        data = read_json_file(path, {})
        platforms = data.get("platforms", {}) if isinstance(data, dict) else {}
        if not isinstance(platforms, dict):
            continue
        total += sum(
            1
            for value in platforms.values()
            if isinstance(value, dict) and value.get("connection_state") == "connected"
        )
    return total


def _login_slots(root: Path) -> dict:
    """Informational only: browser/login occupation never gates registration by itself."""
    try:
        return dict(login_capacity.capacity_snapshot(root))
    except Exception:
        logger.warning("容量快照中的浏览器会话状态不可读", exc_info=True)
        return {"unavailable": True}


def collect_metrics(root: Path | None = None, *, now: datetime | None = None) -> dict:
    """Aggregate the admission metrics. Raises when a gating file cannot be read."""
    base = Path(root) if root else data_root()
    moment = now or _now()
    with auth.identity_scope(None, None):
        users = read_json_file(base / "users.json", {})
        if not isinstance(users, dict):
            users = {}
        records = {name: value for name, value in users.items() if isinstance(value, dict)}
        seen = _presence(base)
        window = timedelta(days=settings.CAPACITY_ACTIVE_WINDOW_DAYS)
        active_users = 0
        for name, record in records.items():
            if record.get("status") != "active":
                continue
            latest = _latest_activity(record, seen.get(name))
            if latest is not None and moment - latest <= window:
                active_users += 1
        metrics = {
            "total_users": sum(1 for value in records.values() if value.get("status") != "deleting"),
            "active_users": active_users,
            "connected_platforms": _connected_platforms(base),
            "active_window_days": settings.CAPACITY_ACTIVE_WINDOW_DAYS,
        }
        metrics["login_slots"] = _login_slots(base)
    return metrics


def _compute(base: Path, moment: datetime) -> CapacityDecision:
    manual = not settings.REGISTRATION_ENABLED
    limits = thresholds()
    metrics = None
    check_failed = False
    if settings.CAPACITY_GUARD_ENABLED:
        try:
            metrics = collect_metrics(base, now=moment)
        except Exception:
            check_failed = True
            logger.exception("容量阈值检查失败，按 fail-closed 暂停新注册")

    reasons: list[str] = []
    if manual:
        reasons.append(REASON_MANUAL)
    if check_failed:
        reasons.append(REASON_CHECK_FAILED)
    elif metrics is not None:
        for reason, field in _GATES:
            limit = limits[field]
            if limit > 0 and metrics[field] >= limit:
                reasons.append(reason)

    return CapacityDecision(
        registration_open=not reasons,
        reason=reasons[0] if reasons else None,
        reasons=tuple(reasons),
        metrics=metrics,
        thresholds=limits,
        manual_pause=manual,
        checked_at=moment.isoformat(),
    )


def _record_state(base: Path, decision: CapacityDecision) -> None:
    """Keep a username-free latch record of the last state change for operators."""
    key = str(base)
    signature = (decision.registration_open, decision.reasons)
    with _latch_lock:
        if _last_latch.get(key) == signature:
            return
        _last_latch[key] = signature
    if not settings.CAPACITY_GUARD_ENABLED:
        return
    record = {
        "version": 1,
        "updated_at": decision.checked_at,
        "registration_open": decision.registration_open,
        "reason": decision.reason,
        "reasons": list(decision.reasons),
        "thresholds": decision.thresholds,
        "metrics": decision.metrics,
    }
    try:
        locked_json_update(base / STATE_FILE, {}, lambda _: record)
    except Exception:
        logger.warning("容量状态记录写入失败；注册开关仍以实时统计为准", exc_info=True)


def reset_cache() -> None:
    with _cache_lock:
        _cache.update(key=None, at=0.0, value=None)


def evaluate(root: Path | None = None, *, now: datetime | None = None, force: bool = False) -> CapacityDecision:
    """Return the current admission decision.

    The result is memoized for a very short window so an anonymous page view
    cannot turn every request into a full data-directory scan.
    """
    base = Path(root) if root else data_root()
    moment = now or _now()
    key = str(base)
    if not force:
        with _cache_lock:
            if _cache["key"] == key and (time.monotonic() - _cache["at"]) < _CACHE_TTL_SECONDS:
                return _cache["value"]
    decision = _compute(base, moment)
    with _cache_lock:
        _cache.update(key=key, at=time.monotonic(), value=decision)
    _record_state(base, decision)
    return decision


def registration_open(root: Path | None = None) -> bool:
    return evaluate(root).registration_open


def registration_notice(decision: CapacityDecision | None = None) -> dict:
    """Public, username-free copy for the register page and the API error."""
    decision = decision or evaluate()
    if decision.registration_open:
        return {"open": True, "reason": None, "reasons": [], "title": "", "badge": "",
                "paragraphs": [], "note": "", "thanks": "", "summary": ""}
    if decision.reason == REASON_MANUAL:
        copy = _MANUAL_COPY
    elif decision.reason == REASON_CHECK_FAILED:
        copy = _CHECK_COPY
    else:
        copy = _CAPACITY_COPY
    return {
        "open": False,
        "reason": decision.reason,
        "reasons": list(decision.reasons),
        "title": copy["title"],
        "badge": copy["badge"],
        "paragraphs": list(copy["paragraphs"]),
        "note": copy["note"],
        "thanks": copy["thanks"],
        "summary": copy["summary"],
    }


def closed_summary(decision: CapacityDecision) -> str:
    return registration_notice(decision)["summary"]


def remember_activity(username: str, root: Path | None = None, *, now: datetime | None = None) -> bool:
    """Best-effort presence stamp; a failure must never break the request."""
    username = (username or "").strip()
    if not username or not settings.CAPACITY_GUARD_ENABLED:
        return False
    base = Path(root) if root else data_root()
    moment = now or _now()
    key = (str(base), username)
    current = time.monotonic()
    with _touch_lock:
        previous = _last_touch.get(key)
        if previous is not None and current - previous < _TOUCH_MIN_INTERVAL_SECONDS:
            return False
        _last_touch[key] = current
    try:
        cutoff = moment - timedelta(days=_PRESENCE_RETENTION_DAYS)
        stamp = moment.isoformat()

        def apply(data):
            payload = data if isinstance(data, dict) else {}
            seen = payload.get("seen")
            seen = dict(seen) if isinstance(seen, dict) else {}
            seen[username] = stamp
            for name, value in list(seen.items()):
                parsed = _parse_time(value)
                if parsed is None or parsed < cutoff:
                    seen.pop(name, None)
            return {"version": 1, "seen": seen}

        locked_json_update(base / PRESENCE_FILE, {"version": 1, "seen": {}}, apply)
    except Exception:
        logger.warning("最近活动记录写入失败；容量判断继续使用登录时间", exc_info=True)
        with _touch_lock:
            _last_touch.pop(key, None)
        return False
    reset_cache()
    return True


def diagnostics(root: Path | None = None) -> dict:
    """Aggregate operator snapshot; also reports metrics while the guard is disabled."""
    base = Path(root) if root else data_root()
    decision = evaluate(base, force=True)
    snapshot = decision.as_dict()
    snapshot["guard_enabled"] = bool(settings.CAPACITY_GUARD_ENABLED)
    if snapshot["metrics"] is None:
        try:
            snapshot["metrics"] = collect_metrics(base)
        except Exception:
            snapshot["metrics"] = None
            snapshot["metrics_error"] = True
    return snapshot
