"""Private Apple Calendar subscription token storage."""
import hmac
import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from storage import locked_json_update, read_json_file
from user_paths import DATA_DIR, user_dir

CST = timezone(timedelta(hours=8))


def _token_file(username: str) -> Path:
    return user_dir(username) / "apple_calendar.json"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(username: str) -> str:
    token = secrets.token_urlsafe(32)

    def replace_token(_data):
        return {"token_hash": _token_hash(token)}

    locked_json_update(_token_file(username), {}, replace_token)
    return token


def revoke_token(username: str) -> bool:
    path = _token_file(username)
    revoked = {"value": False}

    def remove_token(data):
        revoked["value"] = bool(data.pop("token_hash", None))
        return data

    locked_json_update(path, {}, remove_token)
    return revoked["value"]


def username_for_token(token: str) -> str | None:
    if not token or not (DATA_DIR / "users").exists():
        return None
    for path in (DATA_DIR / "users").iterdir():
        if not path.is_dir():
            continue
        stored = read_json_file(path / "apple_calendar.json", {}).get("token_hash")
        if stored and hmac.compare_digest(stored, _token_hash(token)):
            return path.name
    return None


def _escape_ics(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _description(item: dict) -> str | None:
    parts = [str(item.get("source") or "")]
    if item.get("course"):
        parts.append(str(item["course"]))
    if item.get("url"):
        parts.append(str(item["url"]))
    return "\n".join(part for part in parts if part) or None


def build_calendar(username: str, items: list[dict], now: datetime) -> str:
    del username
    now_utc = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Canvas Dashboard//Apple Calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    for item in items:
        if item.get("done"):
            continue
        source = str(item.get("source") or "task").lower()
        item_id = str(item.get("id") or "unknown")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{source}-{item_id}@canvas-dashboard",
            f"DTSTAMP:{now_utc}",
        ])
        due_ts = item.get("due_ts")
        if due_ts:
            try:
                due_at = datetime.fromisoformat(str(due_ts).replace("Z", "+00:00"))
            except ValueError:
                lines.pop()
                lines.pop()
                lines.pop()
                continue
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=CST)
            due_at = due_at.astimezone(CST)
            lines.extend([
                f"DTSTART;TZID=Asia/Shanghai:{due_at.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID=Asia/Shanghai:{(due_at + timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')}",
            ])
        else:
            try:
                due_day = date.fromisoformat(str(item.get("due_date") or ""))
            except ValueError:
                lines.pop()
                lines.pop()
                lines.pop()
                continue
            lines.extend([
                f"DTSTART;VALUE=DATE:{due_day.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(due_day + timedelta(days=1)).strftime('%Y%m%d')}",
            ])
        lines.append(f"SUMMARY:{_escape_ics(str(item.get('title') or 'Untitled task'))}")
        description = _description(item)
        if description:
            lines.append(f"DESCRIPTION:{_escape_ics(description)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
