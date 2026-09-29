"""Shared helpers for platform item state and todo responses."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

from storage import locked_json_update, read_json_file, write_json_file

STATE_KEYS = ("hidden", "highlighted", "deleted", "completed")
DEFAULT_STATE = {"hidden": [], "highlighted": [], "deleted": [], "completed": [], "overrides": {}}
VALID_STATE_ACTIONS = {"hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete"}


CST = timezone(timedelta(hours=8))


def _parse_due_datetime(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    if len(raw) == 10:
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").date()
            return datetime.combine(d, datetime.max.time().replace(microsecond=0), tzinfo=CST)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=CST)
        return dt.astimezone(CST)
    except (ValueError, TypeError):
        return None


def normalize_state(state: dict | None, id_type: Callable = str) -> dict:
    raw = state or {}
    normalized = {
        key: [id_type(item) for item in raw.get(key, [])]
        for key in STATE_KEYS
    }
    overrides = raw.get("overrides", {})
    normalized["overrides"] = {
        str(item_id): {field: value for field, value in patch.items() if field in {"title", "due_ts"}}
        for item_id, patch in overrides.items()
        if isinstance(patch, dict)
    } if isinstance(overrides, dict) else {}
    if raw.get("expired_deleted"):
        normalized["expired_deleted"] = [id_type(item) for item in raw["expired_deleted"]]
    return normalized


class PlatformStateStore:
    def __init__(self, state_path: Callable[[str], Path], id_type: Callable = str):
        self._state_path = state_path
        self._id_type = id_type

    def load(self, username: str) -> dict:
        return normalize_state(read_json_file(self._state_path(username), DEFAULT_STATE.copy()), self._id_type)

    def save(self, username: str, state: dict) -> dict:
        normalized = normalize_state(state, self._id_type)
        def apply(raw):
            permanent = set(normalize_state(raw, self._id_type).get("expired_deleted", []))
            permanent.update(normalized.get("expired_deleted", []))
            if permanent:
                normalized["expired_deleted"] = sorted(permanent)
                normalized["deleted"] = list(dict.fromkeys(normalized["deleted"] + sorted(permanent)))
            return normalized
        return locked_json_update(self._state_path(username), DEFAULT_STATE.copy(), apply)

    def update(self, username: str, action: str, item_id) -> dict:
        item_id = self._id_type(item_id)

        def apply_update(raw_state):
            state = normalize_state(raw_state, self._id_type)
            if item_id in state.get("expired_deleted", []):
                return state
            if action == "hide" and item_id not in state["hidden"]:
                state["hidden"].append(item_id)
            elif action == "unhide":
                state["hidden"] = [existing for existing in state["hidden"] if existing != item_id]
            elif action == "highlight" and item_id not in state["highlighted"]:
                state["highlighted"].append(item_id)
            elif action == "unhighlight":
                state["highlighted"] = [existing for existing in state["highlighted"] if existing != item_id]
            elif action == "delete" and item_id not in state["deleted"]:
                state["deleted"].append(item_id)
                state["hidden"] = [existing for existing in state["hidden"] if existing != item_id]
                state["highlighted"] = [existing for existing in state["highlighted"] if existing != item_id]
            elif action == "undelete":
                state["deleted"] = [existing for existing in state["deleted"] if existing != item_id]
            elif action == "complete" and item_id not in state["completed"]:
                state["completed"].append(item_id)
            elif action == "uncomplete":
                state["completed"] = [existing for existing in state["completed"] if existing != item_id]
            return state

        return locked_json_update(self._state_path(username), DEFAULT_STATE.copy(), apply_update)

    def update_override(self, username: str, item_id, patch: dict | None = None, restore: bool = False) -> dict:
        item_id = self._id_type(item_id)
        allowed = {field: value for field, value in (patch or {}).items() if field in {"title", "due_ts"}}
        def apply_update(raw_state):
            state = normalize_state(raw_state, self._id_type)
            if item_id in state.get("expired_deleted", []):
                return state
            key = str(item_id)
            if restore:
                state["overrides"].pop(key, None)
            elif allowed:
                state["overrides"][key] = {**state["overrides"].get(key, {}), **allowed}
            return state
        return locked_json_update(self._state_path(username), DEFAULT_STATE.copy(), apply_update)

    def delete_expired_completed(self, username: str, items: list[dict], now: datetime) -> dict:
        """Recheck completion and effective deadline inside the state lock."""
        def apply_update(raw_state):
            state = normalize_state(raw_state, self._id_type)
            expired = _expired_completed_ids(items, state, now)
            if expired:
                permanent = state.setdefault("expired_deleted", [])
                for item_id in expired:
                    if item_id not in state["deleted"]:
                        state["deleted"].append(item_id)
                    if item_id not in permanent:
                        permanent.append(item_id)
                for field in ("hidden", "highlighted", "completed"):
                    state[field] = [item for item in state[field] if item not in expired]
            return state
        return locked_json_update(self._state_path(username), DEFAULT_STATE.copy(), apply_update)

    def delete_expired_hidden(self, username: str, expired_ids: list) -> dict:
        if not expired_ids:
            return self.load(username)
        expired_set = set(self._id_type(i) for i in expired_ids)

        def apply_update(raw_state):
            state = normalize_state(raw_state, self._id_type)
            state["hidden"] = [item for item in state["hidden"] if item not in expired_set]
            for item in expired_set:
                if item not in state["deleted"]:
                    state["deleted"].append(item)
            return state

        return locked_json_update(self._state_path(username), DEFAULT_STATE.copy(), apply_update)


def _auto_delete_expired_hidden(items: list[dict], state: dict, now: datetime) -> list:
    expired_ids = []
    if now.tzinfo is None:
        now = now.replace(tzinfo=CST)
    else:
        now = now.astimezone(CST)
    overrides = state.get("overrides", {})
    for item in items:
        item_id = item.get("id")
        if item_id not in state["hidden"]:
            continue
        override = overrides.get(str(item_id), {}) if isinstance(overrides, dict) else {}
        raw_due = override.get("due_ts", item.get("due_ts")) if "due_ts" in override else item.get("due_ts")
        if not raw_due:
            continue
        due_dt = _parse_due_datetime(raw_due)
        if due_dt is None:
            continue
        if due_dt < now:
            expired_ids.append(item_id)
    for item_id in expired_ids:
        if item_id in state["hidden"]:
            state["hidden"].remove(item_id)
        if item_id not in state["deleted"]:
            state["deleted"].append(item_id)
    return expired_ids


def _expired_completed_ids(items, state, now):
    now = now.replace(tzinfo=CST) if now.tzinfo is None else now.astimezone(CST)
    completed = set(state.get("completed", []))
    overrides = state.get("overrides", {})
    expired = []
    for item in items:
        item_id = item.get("id")
        if item_id in state.get("deleted", []):
            continue
        if item_id not in completed and not item.get("done"):
            continue
        patch = overrides.get(str(item_id), {})
        due = _parse_due_datetime(patch.get("due_ts", item.get("due_ts")))
        if due and due < now:
            expired.append(item_id)
    return expired


def build_platform_todos_response(
    result: dict,
    state: dict,
    *,
    items_key: str = "data",
    save_state: Callable[[dict], None] | None = None,
    expire_hidden: Callable[[list], None] | None = None,
    now: datetime | None = None,
    auto_delete_expired_hidden: bool = False,
    expire_completed: Callable[[list[dict], datetime], dict] | None = None,
) -> dict:
    response = dict(result)
    # Callers already loaded state through their typed store (Canvas/好课 use
    # integer IDs; the other platforms use strings).  Do not coerce it again.
    input_state = state or {}
    state = {key: list(input_state.get(key, [])) for key in STATE_KEYS}
    raw_overrides = input_state.get("overrides", {})
    state["overrides"] = raw_overrides if isinstance(raw_overrides, dict) else {}
    items = [dict(item) for item in response.get(items_key, [])]
    if expire_completed is not None and now is not None and _expired_completed_ids(items, state, now):
        state = expire_completed(items, now)

    if auto_delete_expired_hidden and now is not None:
        expired_ids = _auto_delete_expired_hidden(items, state, now)
        if expired_ids:
            if expire_hidden is not None:
                expire_hidden(expired_ids)
            elif save_state is not None:
                save_state(state)

    deleted = set(state["deleted"])
    completed = set(state["completed"])
    for item in items:
        override = state["overrides"].get(str(item.get("id")), {})
        if override:
            item["platform_title"] = item.get("title")
            item["platform_due_ts"] = item.get("due_ts")
            item.update(override)
            item["has_local_override"] = True
        # Normalize the response projection, including old Canvas caches and
        # local date overrides. Never rewrite the upstream cache for display.
        if item.get("due_ts"):
            try:
                due = datetime.fromisoformat(str(item["due_ts"]).replace("Z", "+00:00"))
                if due.tzinfo:
                    due = due.astimezone(timezone(timedelta(hours=8)))
                item["due_str"] = due.strftime("%Y-%m-%d" if due.hour == due.minute == 0 else "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass
        elif "due_ts" in override:
            item["due_str"] = "—"
        if item.get("id") in completed:
            item["done"] = True
            item["local_completed"] = True
    response["data"] = [item for item in items if item.get("id") not in deleted]
    response["hidden"] = state["hidden"]
    response["highlighted"] = state["highlighted"]
    response["deleted"] = state["deleted"]
    response["completed"] = state["completed"]
    response["overrides"] = state["overrides"]
    return response
