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
    if item.get("description"):
        return str(item["description"])
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
        explicit_uid = str(item.get("uid") or "").replace("\r", "").replace("\n", "")
        event_uid = explicit_uid or f"{source}-{item_id}@canvas-dashboard"
        event_lines = [
            "BEGIN:VEVENT",
            f"UID:{event_uid}",
            f"DTSTAMP:{now_utc}",
        ]
        start_dt = item.get("start_dt")
        end_dt = item.get("end_dt")
        due_ts = item.get("due_ts")
        due_date = item.get("due_date")
        if start_dt:
            try:
                if isinstance(start_dt, str):
                    start_at = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                else:
                    start_at = start_dt
                if start_at.tzinfo is None:
                    start_at = start_at.replace(tzinfo=CST)
                start_at = start_at.astimezone(CST)
                if end_dt:
                    if isinstance(end_dt, str):
                        end_at = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                    else:
                        end_at = end_dt
                    if end_at.tzinfo is None:
                        end_at = end_at.replace(tzinfo=CST)
                    end_at = end_at.astimezone(CST)
                else:
                    end_at = start_at + timedelta(hours=1)
            except (ValueError, TypeError):
                continue
            event_lines.extend([
                f"DTSTART;TZID=Asia/Shanghai:{start_at.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID=Asia/Shanghai:{end_at.strftime('%Y%m%dT%H%M%S')}",
            ])
        elif due_ts:
            try:
                due_at = datetime.fromisoformat(str(due_ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=CST)
            due_at = due_at.astimezone(CST)
            event_lines.extend([
                f"DTSTART;TZID=Asia/Shanghai:{due_at.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID=Asia/Shanghai:{(due_at + timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')}",
            ])
        elif due_date:
            try:
                due_day = date.fromisoformat(str(due_date))
            except ValueError:
                continue
            event_lines.extend([
                f"DTSTART;VALUE=DATE:{due_day.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(due_day + timedelta(days=1)).strftime('%Y%m%d')}",
            ])
        else:
            continue

        event_lines.append(f"SUMMARY:{_escape_ics(str(item.get('title') or 'Untitled task'))}")
        if item.get("location"):
            event_lines.append(f"LOCATION:{_escape_ics(str(item['location']))}")
        description = _description(item)
        if description:
            event_lines.append(f"DESCRIPTION:{_escape_ics(description)}")
        event_lines.append("END:VEVENT")
        lines.extend(event_lines)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
