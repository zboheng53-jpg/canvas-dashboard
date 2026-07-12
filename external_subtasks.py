"""Per-user subtasks attached to external-platform todo items."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from storage import locked_json_update, read_json_file
from user_paths import user_dir

SUPPORTED_SOURCES = {"canvas", "haoke", "zhixuemeng", "zhihuishu"}


class ExternalSubtasksDataError(RuntimeError):
    """Raised when the external-subtasks store is not a JSON object."""


def _subtasks_file(username: str):
    return user_dir(username) / "external_subtasks.json"


def _record_key(source: str, item_id) -> str:
    if source not in SUPPORTED_SOURCES:
        raise ValueError("Unsupported external subtask source")
    if item_id is None:
        raise ValueError("External subtask item id is required")
    item_id = str(item_id).strip()
    if not item_id:
        raise ValueError("External subtask item id is required")
    return f"{source}:{item_id}"


def _validate_records(records, path):
    if not isinstance(records, dict):
        raise ExternalSubtasksDataError(
            f"Invalid external subtasks data shape at {path}; expected a JSON object"
        )
    return records


def _load_records(username: str) -> dict:
    path = _subtasks_file(username)
    return _validate_records(read_json_file(path, {}), path)


def save_subtasks(username: str, source: str, item_id, subtasks: list) -> list:
    """Atomically replace subtasks for one external-platform item."""
    key = _record_key(source, item_id)
    if not isinstance(subtasks, list):
        raise ValueError("Subtasks must be a list")
    saved_subtasks = copy.deepcopy(subtasks)
    path = _subtasks_file(username)

    def replace_record(records):
        records = dict(_validate_records(records, path))
        records[key] = {
            "subtasks": saved_subtasks,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return records

    locked_json_update(path, {}, replace_record)
    return copy.deepcopy(saved_subtasks)


def load_subtasks(username: str, source: str, item_id) -> list:
    """Load subtasks for one external-platform item, or an empty list."""
    record = _load_records(username).get(_record_key(source, item_id), {})
    return copy.deepcopy(record.get("subtasks", []))


def attach_subtasks(username: str, source: str, result: dict) -> dict:
    """Return a copied API response with subtasks attached to every data item."""
    if source not in SUPPORTED_SOURCES:
        raise ValueError("Unsupported external subtask source")
    response = copy.deepcopy(result)
    records = _load_records(username)
    for item in response.get("data", []):
        item["subtasks"] = copy.deepcopy(records.get(_record_key(source, item.get("id")), {}).get("subtasks", []))
    return response
