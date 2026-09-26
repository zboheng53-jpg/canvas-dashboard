"""Persistent per-user subtasks for imported platform assignments."""
from datetime import datetime, timezone
from storage import locked_json_update, read_json_file
from user_paths import user_dir

SUPPORTED_SOURCES = frozenset({"canvas", "haoke", "zhixuemeng", "zhihuishu", "ketangpai", "tongjioj"})
DEFAULT_SUBTASKS = {}


def _path(username: str):
    return user_dir(username) / "external_subtasks.json"


def _key(source: str, item_id) -> str:
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported external subtask source: {source}")
    item_id_str = str(item_id).strip()
    if not item_id_str:
        raise ValueError("item id is required for external subtask")
    return f"{source}:{item_id_str}"


def load_subtasks(username: str, source: str, item_id) -> list:
    """Load subtasks for a specific platform item."""
    records = read_json_file(_path(username), DEFAULT_SUBTASKS)
    k = _key(source, item_id)
    return list(records.get(k, {}).get("subtasks", []))


def save_subtasks(username: str, source: str, item_id, subtasks: list) -> list:
    """Atomically save subtasks for a specific platform item."""
    if not isinstance(subtasks, list):
        raise ValueError("subtasks must be a list")

    validated_subtasks = []
    for idx, s in enumerate(subtasks, 1):
        if not isinstance(s, dict):
            continue
        text = str(s.get("text", "")).strip()
        if not text:
            continue
        s_id = s.get("id")
        if s_id is None:
            s_id = idx
        validated_subtasks.append({
            "id": s_id,
            "text": text,
            "done": bool(s.get("done", False)),
            "due_date": s.get("due_date") or None,
        })

    k = _key(source, item_id)

    def update_fn(records: dict) -> dict:
        records[k] = {
            "subtasks": validated_subtasks,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return records

    updated = locked_json_update(_path(username), DEFAULT_SUBTASKS, update_fn)
    return list(updated.get(k, {}).get("subtasks", []))


def attach_subtasks(username: str, source: str, payload):
    """Attach stored subtasks into platform API response items."""
    records = read_json_file(_path(username), DEFAULT_SUBTASKS)
    if isinstance(payload, dict):
        result = dict(payload)
        for list_key in ("data", "items"):
            if list_key in result and isinstance(result[list_key], list):
                result[list_key] = [
                    {
                        **item,
                        "subtasks": list(
                            records.get(_key(source, item.get("id")), {}).get("subtasks", [])
                        ),
                    }
                    if isinstance(item, dict)
                    else item
                    for item in result[list_key]
                ]
        return result
    elif isinstance(payload, list):
        return [
            {
                **item,
                "subtasks": list(
                    records.get(_key(source, item.get("id")), {}).get("subtasks", [])
                ),
            }
            if isinstance(item, dict)
            else item
            for item in payload
        ]
    return payload
