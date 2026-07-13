"""Per-user subtasks attached to external-platform todo items."""
from __future__ import annotations

import copy
import re
from datetime import date, datetime, timezone

from storage import locked_json_update, read_json_file
from user_paths import user_dir

SUPPORTED_SOURCES = {"canvas", "haoke", "zhixuemeng", "zhihuishu"}
_UNSPECIFIED_VERSION = object()


class ExternalSubtasksDataError(RuntimeError):
    """Raised when the external-subtasks store is not a JSON object."""


def _subtasks_file(username: str):
    return user_dir(username) / "external_subtasks.json"


def _record_key(source: str, item_id) -> str:
    if not isinstance(source, str) or source not in SUPPORTED_SOURCES:
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


def _validate_subtasks(subtasks: list) -> None:
    if not isinstance(subtasks, list):
        raise ValueError("Subtasks must be a list")
    for subtask in subtasks:
        if not isinstance(subtask, dict):
            raise ValueError("Each subtask must be an object")
        due_date = subtask.get("due_date")
        if due_date in (None, ""):
            continue
        if not isinstance(due_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
            raise ValueError("Subtask due date must be YYYY-MM-DD")
        try:
            date.fromisoformat(due_date)
        except ValueError as error:
            raise ValueError("Subtask due date must be YYYY-MM-DD") from error


def save_subtasks_with_version(
    username: str, source: str, item_id, subtasks: list, updated_at=_UNSPECIFIED_VERSION
) -> tuple[dict, bool]:
    """Atomically replace subtasks unless the supplied version is stale."""
    key = _record_key(source, item_id)
    _validate_subtasks(subtasks)
    saved_subtasks = copy.deepcopy(subtasks)
    path = _subtasks_file(username)
    result = {"record": None, "conflict": False}

    def replace_record(records):
        records = dict(_validate_records(records, path))
        current = records.get(key, {})
        if not isinstance(current, dict):
            current = {}
        if updated_at is not _UNSPECIFIED_VERSION and updated_at != current.get("updated_at"):
            result["record"] = {
                "subtasks": copy.deepcopy(current.get("subtasks", [])),
                "updated_at": current.get("updated_at"),
            }
            result["conflict"] = True
            return records
        result["record"] = {
            "subtasks": saved_subtasks,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        records[key] = result["record"]
        return records

    locked_json_update(path, {}, replace_record)
    return copy.deepcopy(result["record"]), result["conflict"]


def save_subtasks(username: str, source: str, item_id, subtasks: list) -> list:
    """Atomically replace subtasks for one external-platform item."""
    record, _ = save_subtasks_with_version(username, source, item_id, subtasks)
    return record["subtasks"]


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
        record = records.get(_record_key(source, item.get("id")), {})
        item["subtasks"] = copy.deepcopy(record.get("subtasks", []))
        item["subtasks_updated_at"] = record.get("updated_at")
    return response
