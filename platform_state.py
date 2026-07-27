"""Shared helpers for platform item state and todo responses."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from storage import locked_json_update, read_json_file, write_json_file

STATE_KEYS = ("hidden", "highlighted", "deleted", "completed")
DEFAULT_STATE = {"hidden": [], "highlighted": [], "deleted": [], "completed": [], "overrides": {}}
VALID_STATE_ACTIONS = {"hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete"}


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
    return normalized


class PlatformStateStore:
    def __init__(self, state_path: Callable[[str], Path], id_type: Callable = str):
        self._state_path = state_path
        self._id_type = id_type

    def load(self, username: str) -> dict:
        return normalize_state(read_json_file(self._state_path(username), DEFAULT_STATE.copy()), self._id_type)

    def save(self, username: str, state: dict) -> dict:
        normalized = normalize_state(state, self._id_type)
        write_json_file(self._state_path(username), normalized)
        return normalized

    def update(self, username: str, action: str, item_id) -> dict:
        item_id = self._id_type(item_id)

        def apply_update(raw_state):
            state = normalize_state(raw_state, self._id_type)
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
            key = str(item_id)
            if restore:
                state["overrides"].pop(key, None)
            elif allowed:
                state["overrides"][key] = {**state["overrides"].get(key, {}), **allowed}
            return state
        return locked_json_update(self._state_path(username), DEFAULT_STATE.copy(), apply_update)


def _auto_delete_expired_hidden(items: list[dict], state: dict, now: datetime) -> bool:
    changed = False
    for item in items:
        item_id = item.get("id")
        if item_id not in state["hidden"] or not item.get("due_ts"):
            continue
        try:
            due_dt = datetime.fromisoformat(item["due_ts"])
        except (ValueError, TypeError):
            continue
        if due_dt < now:
            state["hidden"].remove(item_id)
            if item_id not in state["deleted"]:
                state["deleted"].append(item_id)
            changed = True
    return changed


def build_platform_todos_response(
    result: dict,
    state: dict,
    *,
    items_key: str = "data",
    save_state: Callable[[dict], None] | None = None,
    now: datetime | None = None,
    auto_delete_expired_hidden: bool = True,
) -> dict:
    response = dict(result)
    # Callers already loaded state through their typed store (Canvas/好课 use
    # integer IDs; the other platforms use strings).  Do not coerce it again.
    input_state = state or {}
    state = {key: list(input_state.get(key, [])) for key in STATE_KEYS}
    raw_overrides = input_state.get("overrides", {})
    state["overrides"] = raw_overrides if isinstance(raw_overrides, dict) else {}
    items = [dict(item) for item in response.get(items_key, [])]

    if auto_delete_expired_hidden and now is not None:
        changed = _auto_delete_expired_hidden(items, state, now)
        if changed and save_state is not None:
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
