"""Fetch Canvas assignments from iCal calendar feed.

The calendar feed URL includes an authentication token so no browser
login is needed.  The feed is standard iCal format (RFC 5545).
"""
import logging
from datetime import datetime, timezone, timedelta

import hashlib
import ipaddress
import requests
import socket
from icalendar import Calendar
from urllib.parse import urlsplit

from platform_state import PlatformStateStore
from storage import read_json_file, write_json_file
from user_paths import user_dir

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))
_state_store = PlatformStateStore(lambda username: user_dir(username) / "canvas_state.json", int)


def get_feed_url(username):
    config_file = user_dir(username) / "config.json"
    return read_json_file(config_file, {}).get("calendar_feed_url")


def validate_feed_url(url: str) -> tuple[bool, str | None]:
    parsed = urlsplit(url)
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
    return True, None


def save_feed_url(username, url):
    ok, error = validate_feed_url(url)
    if not ok:
        return False, error
    config_file = user_dir(username) / "config.json"
    config = read_json_file(config_file, {})
    config["calendar_feed_url"] = url
    write_json_file(config_file, config)
    return True, None


def has_feed_url(username):
    return bool(get_feed_url(username))


def _extract_stable_id(url, uid):
    """Extract Canvas assignment/event ID from URL fragment, fall back to UID hash."""
    if url and "#" in url:
        fragment = url.rsplit("#", 1)[1]
        for prefix in ("assignment_", "calendar_event_"):
            if fragment.startswith(prefix):
                try:
                    return int(fragment[len(prefix):])
                except ValueError:
                    pass
    return int(hashlib.sha256(uid.encode("utf-8")).hexdigest(), 16) % 1000000


def _migrate_state_from_cache(username):
    """Migrate old hash-based IDs in state to stable assignment IDs from URL fragments.

    Reads the current cache (which may have old hash IDs), extracts the stable
    assignment ID from each item's URL, and remaps state entries accordingly.
    Should be called BEFORE overwriting the cache with new data.
    """
    state_file = user_dir(username) / "canvas_state.json"
    cache_file = user_dir(username) / "canvas_cache.json"
    if not state_file.exists() or not cache_file.exists():
        return
    try:
        cache_items = read_json_file(cache_file, [])
    except Exception:
        return

    # Build mapping: old hash ID → stable assignment ID (from URL fragment)
    mapping = {}
    for item in cache_items:
        url = item.get("url", "")
        old_id = item.get("id")
        new_id = _extract_stable_id(url, str(old_id))
        if old_id != new_id:
            mapping[old_id] = new_id
    if not mapping:
        return

    state = load_state(username)
    changed = False
    for key in ("hidden", "highlighted", "deleted"):
        new_list = []
        for oid in state.get(key, []):
            if oid in mapping:
                new_list.append(mapping[oid])
                changed = True
            else:
                new_list.append(oid)
        state[key] = new_list
    if changed:
        save_state(username, state)
        logger.info(f"Migrated state IDs: {mapping}")


def load_state(username):
    """Load hidden/highlighted Canvas item IDs."""
    return _state_store.load(username)


def save_state(username, state):
    _state_store.save(username, state)


def update_state(username, action, item_id):
    """Apply a state action: hide, unhide, highlight, unhighlight."""
    return _state_store.update(username, action, item_id)


def fetch_canvas_planner(username):
    """Fetch incomplete planner items from the Canvas iCal feed."""
    feed_url = get_feed_url(username)
    if not feed_url:
        return {"ok": False, "error": "请先设置日历馈送源 URL", "data": [], "need_setup": True}

    try:
        resp = requests.get(feed_url, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"Calendar feed returned {resp.status_code}")
            return _fallback_cache(username)

        items = _parse_ical(resp.text)
        _migrate_state_from_cache(username)
        cache_file = user_dir(username) / "canvas_cache.json"
        write_json_file(cache_file, items)
        return {"ok": True, "data": items, "cached": False}

    except requests.RequestException as e:
        logger.warning(f"Calendar feed request failed: {e}")
        return _fallback_cache(username)
    except Exception as e:
        logger.error(f"Calendar feed parse error: {e}")
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
        if due_dt < today:
            continue  # expired
        due_ts = due_dt
        if due_dt.hour == 0 and due_dt.minute == 0:
            due_str = due_dt.strftime("%m-%d")
        else:
            due_str = due_dt.strftime("%m-%d %H:%M")

        results.append({
            "id": _extract_stable_id(url, uid),
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
        try:
            items = read_json_file(cache_file, [])
            return {"ok": True, "data": items, "cached": True}
        except Exception:
            pass
    return {"ok": False, "error": "无法获取日历数据，且无缓存数据", "data": []}
