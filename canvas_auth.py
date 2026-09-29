"""Fetch Canvas assignments from iCal calendar feed.

The calendar feed URL includes an authentication token so no browser
login is needed.  The feed is standard iCal format (RFC 5545).
"""
import logging
from datetime import datetime, timezone, timedelta

import hashlib
import ipaddress
import time
import requests
import socket
import settings
import auth
from icalendar import Calendar
from urllib.parse import urlsplit

from platform_state import PlatformStateStore
from storage import locked_json_update, read_json_file, write_json_file
from user_paths import user_dir

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))
_state_store = PlatformStateStore(lambda username: user_dir(username) / "canvas_state.json", str)


def get_feed_url(username):
    config_file = user_dir(username) / "config.json"
    return read_json_file(config_file, {}).get("calendar_feed_url")


def validate_feed_url(url: str) -> tuple[bool, str | None]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (ValueError, TypeError):
        return False, "日历链接格式无效"
    if parsed.scheme != "https":
        return False, "calendar feed URL must use HTTPS"
    if not parsed.hostname or parsed.username or parsed.password:
        return False, "calendar feed URL must use a public hostname"
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
        resolved = {record[4][0] for record in addresses}
    except socket.gaierror:
        return False, "calendar feed hostname could not be resolved"
    if not resolved or any(not ipaddress.ip_address(address).is_global for address in resolved):
        return False, "calendar feed URL must resolve to public addresses"
    if parsed.hostname.lower() not in settings.CANVAS_FEED_HOSTS or port not in (None, 443):
        return False, "请使用受支持的 Canvas 日历链接；其他学校需由维护者配置域名"
    return True, None


def save_feed_url(username, url):
    ok, error = validate_feed_url(url)
    if not ok:
        return False, error
    config_file = user_dir(username) / "config.json"
    def update(config):
        config["calendar_feed_url"] = url
        config["canvas_connection_revision"] = int(config.get("canvas_connection_revision", 0)) + 1
        return config
    with auth.account_operation(username):
        locked_json_update(config_file, {}, update)
    return True, None


def has_feed_url(username):
    return bool(get_feed_url(username))


def remove_feed_url(username):
    config_file = user_dir(username) / "config.json"
    def remove(config):
        config.pop("calendar_feed_url", None)
        config["canvas_connection_revision"] = int(config.get("canvas_connection_revision", 0)) + 1
        return config
    with auth.account_operation(username):
        locked_json_update(config_file, {}, remove)


def _connection_revision(username):
    return read_json_file(user_dir(username) / "config.json", {}).get("canvas_connection_revision", 0)


def _extract_stable_id(url, uid):
    """Extract Canvas assignment/event stable string ID from URL fragment or path or UID."""
    if url:
        if "#" in url:
            fragment = url.rsplit("#", 1)[1]
            for prefix, type_name in (("assignment_", "assignment"), ("calendar_event_", "calendar_event")):
                if fragment.startswith(prefix):
                    obj_id = fragment[len(prefix):]
                    if obj_id.isdigit():
                        return f"canvas:{type_name}:{obj_id}"
        for pattern, type_name in (("/assignments/", "assignment"), ("/calendar_events/", "calendar_event")):
            if pattern in url:
                part = url.split(pattern, 1)[1].split("?")[0].split("#")[0].strip("/")
                if part and part.isdigit():
                    return f"canvas:{type_name}:{part}"
    clean_uid = uid or ""
    uid_hash = hashlib.sha256(clean_uid.encode("utf-8")).hexdigest()
    return f"canvas:event:{uid_hash}"


def _migrate_state_from_cache(username, fresh_items=None):
    """Migrate old IDs in state and subtasks to stable typed assignment/event IDs.

    Reads the current cache, extracts the stable ID from each item's URL,
    and remaps state entries (hidden, highlighted, deleted, completed, overrides)
    and external subtasks accordingly.
    """
    state_file = user_dir(username) / "canvas_state.json"
    cache_file = user_dir(username) / "canvas_cache.json"
    subtasks_file = user_dir(username) / "external_subtasks.json"
    aliases_file = user_dir(username) / "canvas_id_migration.json"

    if not cache_file.exists():
        return
    snapshot = read_json_file(cache_file, [])
    if all(str(item.get("id")).startswith("canvas:") for item in snapshot) and (
        not fresh_items or not any(str(item.get("id")).startswith("canvas:legacy:") for item in snapshot)
    ):
        return
    fresh_by_legacy = {}
    for item in fresh_items or []:
        uid = item.get("uid")
        if uid:
            old_hash = str(int(hashlib.sha256(uid.encode("utf-8")).hexdigest(), 16) % 1000000)
            fresh_by_legacy.setdefault(old_hash, set()).add(str(item["id"]))

    def migrate(cache_items):
        candidates = {}
        replacements = []
        for item in cache_items:
            old_id = str(item.get("id"))
            new_id = old_id
            if old_id.startswith("canvas:legacy:"):
                options = fresh_by_legacy.get(old_id.removeprefix("canvas:legacy:"), set())
                if len(options) == 1:
                    new_id = next(iter(options))
            elif not old_id.startswith("canvas:"):
                url, uid = item.get("url", ""), item.get("uid")
                extracted = _extract_stable_id(url, uid or old_id)
                if not extracted.startswith("canvas:event:") or uid:
                    new_id = extracted
                else:
                    options = fresh_by_legacy.get(old_id, set())
                    new_id = next(iter(options)) if len(options) == 1 else f"canvas:legacy:{old_id}"
            candidates.setdefault(old_id, set()).add(new_id)
            replacements.append({**item, "id": new_id})
        mapping = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1 and key != next(iter(values))}
        ambiguous = {key: sorted(values) for key, values in candidates.items() if len(values) > 1}
        if not mapping and not ambiguous:
            return cache_items

        def save_aliases(data):
            data.setdefault("aliases", {}).update(mapping)
            data.setdefault("ambiguous", {}).update(ambiguous)
            for key in ambiguous:
                data["aliases"].pop(key, None)
            return data
        migration = locked_json_update(aliases_file, {}, save_aliases)

        def mapped(value):
            value = str(value)
            seen = set()
            while value in migration["aliases"] and value not in seen:
                seen.add(value)
                value = migration["aliases"][value]
            return value

        if state_file.exists():
            def migrate_state(state):
                for key in ("hidden", "highlighted", "deleted", "completed"):
                    state[key] = list(dict.fromkeys(mapped(value) for value in state.get(key, [])))
                overrides = dict(state.get("overrides", {}))
                for key, patch in list(overrides.items()):
                    target = mapped(key)
                    if target != key:
                        overrides[target] = {**patch, **overrides.get(target, {})}
                        overrides.pop(key, None)
                state["overrides"] = overrides
                return state
            locked_json_update(state_file, {}, migrate_state)

        if subtasks_file.exists():
            def migrate_subtasks(records):
                for key, value in list(records.items()):
                    if key.startswith("canvas:"):
                        target = "canvas:" + mapped(key[len("canvas:"):])
                        if target != key and target not in records:
                            records[target] = value
                            records.pop(key)
                return records
            locked_json_update(subtasks_file, {}, migrate_subtasks)
        schedules_file = user_dir(username) / "schedule_items.json"
        if schedules_file.exists():
            def migrate_schedule_refs(records):
                for kind in ("recurring", "one_off"):
                    for item in records.get(kind, []):
                        ref = item.get("action_ref")
                        if ref and ref.startswith("canvas:"):
                            item["action_ref"] = "canvas:" + mapped(ref[len("canvas:"):])
                return records
            locked_json_update(schedules_file, {}, migrate_schedule_refs)
        return replacements

    # Serialize migrations with refresh publication; reread under the cache lock.
    locked_json_update(cache_file, [], migrate)


def resolve_item_id(username, item_id):
    aliases = read_json_file(user_dir(username) / "canvas_id_migration.json", {}).get("aliases", {})
    value, seen = str(item_id), set()
    while value in aliases and value not in seen:
        seen.add(value)
        value = aliases[value]
    return value


def cached_items(username):
    _migrate_state_from_cache(username)
    return read_json_file(user_dir(username) / "canvas_cache.json", [])


def load_state(username):
    """Load hidden/highlighted Canvas item IDs."""
    _migrate_state_from_cache(username)
    return _state_store.load(username)


def save_state(username, state):
    _state_store.save(username, state)


def delete_expired_hidden(username, expired_ids):
    return _state_store.delete_expired_hidden(username, expired_ids)


delete_expired_completed = _state_store.delete_expired_completed


def update_state(username, action, item_id):
    """Apply a state action: hide, unhide, highlight, unhighlight."""
    _migrate_state_from_cache(username)
    return _state_store.update(username, action, resolve_item_id(username, item_id))


def update_override(username, item_id, patch=None, restore=False):
    _migrate_state_from_cache(username)
    return _state_store.update_override(username, resolve_item_id(username, item_id), patch, restore)


def fetch_canvas_planner(username):
    """Fetch incomplete planner items from the Canvas iCal feed."""
    feed_url = get_feed_url(username)
    if not feed_url:
        return {"ok": False, "error": "请先设置日历馈送源 URL", "data": [], "need_setup": True}

    try:
        valid, error = validate_feed_url(feed_url)
        if not valid:
            result = _fallback_cache(username)
            result.update(error=error, refresh_failed=True)
            return result
        # Feed URLs contain a secret. Do not forward it through redirects or
        # allow an arbitrary registered account to target internal services.
        resp = requests.get(feed_url, timeout=30, allow_redirects=False)
        if resp.status_code != 200:
            logger.warning(f"Calendar feed returned {resp.status_code}")
            return _fallback_cache(username)

        items = _parse_ical(resp.text)
        _migrate_state_from_cache(username, items)
        cache_file = user_dir(username) / "canvas_cache.json"
        write_json_file(cache_file, items)
        return {"ok": True, "data": items, "cached": False}

    except requests.RequestException as e:
        logger.warning("Calendar feed request failed (%s)", type(e).__name__)
        return _fallback_cache(username)
    except Exception as e:
        logger.error("Calendar feed parse error (%s)", type(e).__name__)
        return _fallback_cache(username)



def _parse_ical(raw):
    """Parse iCal string and return list of todo dicts (excluding past items)."""
    results = []
    cal = Calendar.from_ical(raw)
    today = datetime.now(CST).replace(hour=0, minute=0, second=0, microsecond=0)

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary", "无标题"))
        description = str(component.get("description", ""))
        url = str(component.get("url", ""))
        uid = str(component.get("uid", summary))

        # Parse due date from DTSTART or DTEND
        due_dt = None
        for attr in ("dtstart", "dtend"):
            raw_dt = component.get(attr)
            if raw_dt:
                due_dt = _to_cst_datetime(raw_dt.dt)
                break

        # Extract course name from description (Canvas format)
        course = ""
        if description:
            for line in description.split("\n"):
                line = line.strip()
                for prefix in ("课程:", "Course:", "课程名称:"):
                    if line.startswith(prefix):
                        course = line.split(":", 1)[1].strip()
                        break
                if course:
                    break

        if not due_dt:
            continue  # no due date
        if due_dt < today - timedelta(days=30):
            continue  # expired beyond 30-day retention window
        due_ts = due_dt
        if due_dt.hour == 0 and due_dt.minute == 0:
            due_str = due_dt.strftime("%Y-%m-%d")
        else:
            due_str = due_dt.strftime("%Y-%m-%d %H:%M")

        results.append({
            "id": _extract_stable_id(url, uid),
            "uid": uid,
            "title": summary,
            "course": course,
            "due_str": due_str,
            "due_ts": due_ts.isoformat() if due_ts else None,
            "type": "作业",
            "type_raw": "assignment",
            "url": url,
        })

    results.sort(key=lambda x: (0 if x["due_ts"] else 1, x["due_ts"] or ""))
    return results


def _to_cst_datetime(dt):
    """Convert various datetime types to CST-aware datetime or None."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CST)
    # date only
    d = datetime.combine(dt, datetime.min.time())
    return d.replace(tzinfo=CST)


def _fallback_cache(username):
    cache_file = user_dir(username) / "canvas_cache.json"
    if cache_file.exists():
        items = cached_items(username)
        migration = read_json_file(user_dir(username) / "canvas_id_migration.json", {})
        result = {"ok": True, "data": items, "cached": True}
        if migration.get("ambiguous"):
            result["migration_ambiguous_ids"] = sorted(migration["ambiguous"])
        return result
    return {"ok": False, "error": "无法获取日历数据，且无缓存数据", "data": []}


CANVAS_CACHE_TTL_SECONDS = 30 * 60


def get_cached_todos(username: str, now: float | None = None) -> dict:
    """Return cached Canvas items with staleness indication."""
    cache_file = user_dir(username) / "canvas_cache.json"
    if not cache_file.exists():
        return {
            "ok": False,
            "data": [],
            "cached": True,
            "has_cache": False,
            "stale": True,
            "fetched_at": None,
        }
    try:
        items = cached_items(username)
        mtime = cache_file.stat().st_mtime
    except OSError:
        return {
            "ok": False,
            "data": [],
            "cached": True,
            "has_cache": False,
            "stale": True,
            "fetched_at": None,
        }
    now = now or time.time()
    stale = (now - mtime) > CANVAS_CACHE_TTL_SECONDS
    return {
        "ok": True,
        "data": items,
        "cached": True,
        "has_cache": True,
        "fetched_at": mtime,
        "stale": stale,
    }


def _run_background_refresh(username: str, initial_identity=None, revision=None) -> None:
    import http_sync
    import platform_sync

    initial_identity = initial_identity or http_sync.get_account_identity(username)
    revision = _connection_revision(username) if revision is None else revision
    if initial_identity is None:
        return
    feed_url = get_feed_url(username)
    if not feed_url:
        return
    valid, error = validate_feed_url(feed_url)
    try:
        if not valid:
            raise ValueError("invalid_feed_url")
        resp = requests.get(feed_url, timeout=30, allow_redirects=False)
        if resp.status_code != 200:
            raise ValueError(f"http_{resp.status_code}")
        items = _parse_ical(resp.text)
    except Exception as exc:
        with auth.account_operation(username):
            if http_sync.get_account_identity(username) == initial_identity and has_feed_url(username) and _connection_revision(username) == revision:
                platform_sync.record_result(
                    username, "canvas", ok=False,
                    has_cache=(user_dir(username) / "canvas_cache.json").exists(),
                    error_code=type(exc).__name__, error_message="Canvas 刷新失败，已保留上次数据",
                )
        return {"ok": False}

    # Check identity and connection before writeback!
    with auth.account_operation(username):
        if http_sync.get_account_identity(username) != initial_identity or not has_feed_url(username) or _connection_revision(username) != revision:
            return
        _migrate_state_from_cache(username, items)
        cache_file = user_dir(username) / "canvas_cache.json"
        write_json_file(cache_file, items)
        platform_sync.record_result(username, "canvas", ok=True, has_cache=True)


def start_background_refresh(username: str) -> bool:
    """Submit background Canvas refresh to unified bounded executor."""
    if not has_feed_url(username):
        return False
    import http_sync
    identity = http_sync.get_account_identity(username)
    revision = _connection_revision(username)
    return http_sync.submit_http_sync(
        username,
        "canvas",
        lambda: _run_background_refresh(username, identity, revision),
        is_connected_fn=has_feed_url,
    )


def is_refreshing(username: str) -> bool:
    """Check if Canvas sync is currently active for user."""
    import http_sync
    return http_sync.is_refreshing(username, "canvas")
