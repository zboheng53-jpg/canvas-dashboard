"""Atomic per-user storage for long-term projects, groups, and tasks."""
import copy
from datetime import date, datetime, timezone, timedelta

from storage import locked_json_update, read_json_file
import user_paths
from action_contract import ActionValidationError, check_version, fingerprint, replay


VERSION = 2
PROJECT_STATUSES = {"active", "completed", "archived"}


def _file(username):
    return user_paths.user_dir(username) / "projects.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _empty_state():
    return {
        "version": VERSION,
        "main_project_id": None,
        "last_viewed_project_id": None,
        "projects": [],
    }


def _int(value, default=0):
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _next_id(values):
    return max((_int(value.get("id")) for value in values if isinstance(value, dict)), default=0) + 1


def _normalize_group(group, fallback_id, fallback_order):
    now = _now()
    return {
        "id": _int(group.get("id"), fallback_id),
        "name": str(group.get("name") or "未命名分组")[:80],
        "sort_order": _int(group.get("sort_order"), fallback_order),
        "created_at": group.get("created_at") or now,
        "updated_at": group.get("updated_at") or group.get("created_at") or now,
    }


def _normalize_task(task, fallback_id, fallback_order, valid_group_ids, legacy=False):
    now = _now()
    name = task.get("name")
    if legacy:
        name = task.get("text")
    done = bool(task.get("done", False))
    group_id = task.get("group_id")
    if group_id not in valid_group_ids:
        group_id = None
    return {
        "id": _int(task.get("id"), fallback_id),
        "name": str(name or "未命名任务"),
        "original_name": task.get("original_name"),
        "deleted_at": task.get("deleted_at"),
        "materials_saved_at": task.get("materials_saved_at"),
        "details": str(task.get("details") or ""),
        "commitment": task.get("commitment") if task.get("commitment") in {"growth", "obligation"} else "legacy",
        "planned_on": task.get("planned_on") or None,
        "estimate_minutes": task.get("estimate_minutes"),
        "request_id": task.get("request_id"),
        "request_fingerprint": task.get("request_fingerprint"),
        "group_id": group_id,
        "due_date": task.get("due_date") or None,
        "done": done,
        "highlighted": bool(task.get("highlighted", False)),
        "is_next_action": bool(task.get("is_next_action", False)) and not done and not task.get("deleted_at"),
        "sort_order": _int(task.get("sort_order"), fallback_order),
        "created_at": task.get("created_at") or now,
        "updated_at": task.get("updated_at") or task.get("created_at") or now,
        "completed_at": (task.get("completed_at") or now) if done else None,
    }


def _pick_default_next_task(groups, tasks, exclude_task_id=None):
    group_order = {group["id"]: (group["sort_order"], group["id"]) for group in groups}
    candidates = [
        task for task in tasks
        if not task.get("done")
        and not task.get("deleted_at")
        and (exclude_task_id is None or task.get("id") != exclude_task_id)
    ]
    if not candidates:
        return None

    def sort_key(task):
        gid = task.get("group_id")
        planned = task.get("planned_on") or "9999-12-31"
        if gid is not None and gid in group_order:
            return (planned, 0, group_order[gid], task.get("sort_order", 0), task.get("id", 0))
        return (planned, 1, (0, 0), task.get("sort_order", 0), task.get("id", 0))

    return min(candidates, key=sort_key)


def _normalize_project(project, fallback_id, fallback_order):
    now = _now()
    groups = []
    used_group_ids = set()
    for index, raw_group in enumerate(project.get("groups") or []):
        if not isinstance(raw_group, dict):
            continue
        group = _normalize_group(raw_group, index + 1, index)
        if group["id"] in used_group_ids:
            group["id"] = max(used_group_ids, default=0) + 1
        used_group_ids.add(group["id"])
        groups.append(group)

    source_tasks = project.get("tasks")
    legacy = not isinstance(source_tasks, list)
    if legacy:
        source_tasks = project.get("goals") or []
    tasks = []
    used_task_ids = set()
    next_action_seen = False
    for index, raw_task in enumerate(source_tasks):
        if not isinstance(raw_task, dict):
            continue
        task = _normalize_task(raw_task, index + 1, index, used_group_ids, legacy=legacy)
        if task.get("deleted_at"):
            continue
        if task["id"] in used_task_ids:
            task["id"] = max(used_task_ids, default=0) + 1
        used_task_ids.add(task["id"])
        if task["is_next_action"]:
            if next_action_seen:
                task["is_next_action"] = False
            next_action_seen = True
        tasks.append(task)

    if not next_action_seen:
        default_next = _pick_default_next_task(groups, tasks)
        if default_next is not None:
            default_next["is_next_action"] = True

    status = project.get("status")
    if status not in PROJECT_STATUSES:
        status = "active"
    completed_at = project.get("completed_at") if status == "completed" else None
    archived_at = project.get("archived_at") if status == "archived" else None
    if status == "completed" and not completed_at:
        completed_at = project.get("updated_at") or now
    if status == "archived" and not archived_at:
        archived_at = project.get("updated_at") or now
    material_fields = {}
    if "material_entries" in project:
        entries = project["material_entries"]
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) or type(entry.get("id")) is not int
            or entry["id"] < 1 or not isinstance(entry.get("body"), str)
            for entry in entries
        ) or len({entry["id"] for entry in entries}) != len(entries):
            raise ActionValidationError("资料日志存储格式损坏，未覆盖原数据")
        material_fields = {
            "material_entries": copy.deepcopy(entries),
            "next_material_entry_id": max(_int(project.get("next_material_entry_id"), 1), _next_id(entries)),
        }
    return {
        "id": _int(project.get("id"), fallback_id),
        "name": str(project.get("name") or "未命名项目")[:100],
        "objective": str(project.get("objective") or "")[:240],
        "materials": str(project.get("materials") or ""),
        "deleted_at": project.get("deleted_at"),
        "next_task_id": max(_int(project.get("next_task_id"), 1), _next_id(tasks)),
        "due_date": project.get("due_date") or None,
        "due_highlighted": bool(project.get("due_highlighted", False)),
        "status": status,
        "sort_order": _int(project.get("sort_order"), fallback_order),
        "created_at": project.get("created_at") or now,
        "updated_at": project.get("updated_at") or project.get("created_at") or now,
        "completed_at": completed_at,
        "archived_at": archived_at,
        "groups": groups,
        "tasks": tasks,
        **material_fields,
    }


def _normalize_state(raw):
    if isinstance(raw, list):
        raw = {"version": 1, "projects": raw}
    if not isinstance(raw, dict):
        raw = {}
    projects = []
    used_ids = set()
    for index, raw_project in enumerate(raw.get("projects") or []):
        if not isinstance(raw_project, dict):
            continue
        project = _normalize_project(raw_project, index + 1, index)
        if project.get("deleted_at"):
            continue
        if project["id"] in used_ids:
            project["id"] = max(used_ids, default=0) + 1
        used_ids.add(project["id"])
        projects.append(project)
    active_ids = {project["id"] for project in projects if project["status"] == "active" and not project.get("deleted_at")}
    all_ids = {project["id"] for project in projects if not project.get("deleted_at")}
    main_project_id = raw.get("main_project_id")
    if main_project_id not in active_ids:
        main_project_id = None
    last_viewed_project_id = raw.get("last_viewed_project_id")
    if last_viewed_project_id not in all_ids:
        last_viewed_project_id = None
    return {
        "version": VERSION,
        "main_project_id": main_project_id,
        "last_viewed_project_id": last_viewed_project_id,
        "projects": projects,
        "next_project_id": max(_int(raw.get("next_project_id"), 1), _next_id(projects)),
    }


def load_state(username):
    path = _file(username)
    raw = read_json_file(path, _empty_state())
    normalized = _normalize_state(raw)
    if raw != normalized:
        return locked_json_update(path, _empty_state(), _normalize_state)
    return normalized


def _due_state(due_date, today=None):
    if not due_date:
        return None, None
    try:
        due_day = date.fromisoformat(due_date)
    except (TypeError, ValueError):
        return None, None
    delta = (due_day - (today or date.today())).days
    if delta < 0:
        return "overdue", abs(delta)
    if delta == 0:
        return "today", 0
    return "upcoming", delta


def _project_view(project, today=None, include_deleted=False):
    value = copy.deepcopy(project)
    value.setdefault("material_entries", [])
    if not include_deleted:
        value["tasks"] = [task for task in value["tasks"] if not task.get("deleted_at")]
    value["groups"].sort(key=lambda group: (group["sort_order"], group["id"]))
    value["tasks"].sort(key=lambda task: (task["sort_order"], task["id"]))
    if not any(task.get("is_next_action") for task in value["tasks"] if not task["done"] and not task.get("deleted_at")):
        default_next = _pick_default_next_task(value["groups"], value["tasks"])
        if default_next is not None:
            default_next["is_next_action"] = True
    value["completed_count"] = sum(1 for task in value["tasks"] if task["done"])
    value["pending_count"] = sum(1 for task in value["tasks"] if not task["done"])
    value["due_state"], value["due_days"] = _due_state(value.get("due_date"), today)
    return value


def _ordered_projects(state):
    status_rank = {"active": 0, "completed": 1, "archived": 2}
    main_id = state["main_project_id"]
    return sorted(
        state["projects"],
        key=lambda project: (
            status_rank[project["status"]],
            0 if project["id"] == main_id else 1,
            project["sort_order"],
            project["id"],
        ),
    )


def load_projects(username, include_deleted=False):
    state = load_state(username)
    return [_project_view(project, include_deleted=include_deleted) for project in _ordered_projects(state)
            if include_deleted or not project.get("deleted_at")]


def _mutate(username, mutator):
    result = {}

    def update(raw):
        state = _normalize_state(raw)
        mutator(state, result)
        return _normalize_state(state)

    state = locked_json_update(_file(username), _empty_state(), update)
    return state, result


def _find_project(state, project_id, include_deleted=False):
    return next((project for project in state["projects"] if project["id"] == project_id
                 and (include_deleted or not project.get("deleted_at"))), None)


def _find_group(project, group_id):
    return next((group for group in project["groups"] if group["id"] == group_id), None)


def _find_task(project, task_id, include_deleted=False):
    return next((task for task in project["tasks"] if task["id"] == task_id
                 and (include_deleted or not task.get("deleted_at"))), None)


def create_project(username, payload):
    def mutation(state, result):
        now = _now()
        active_orders = [project["sort_order"] for project in state["projects"] if project["status"] == "active"]
        project = {
            "id": state["next_project_id"],
            "name": payload["name"],
            "objective": payload.get("objective", ""),
            "materials": payload.get("materials", ""),
            "due_date": payload.get("due_date"),
            "due_highlighted": False,
            "status": "active",
            "sort_order": max(active_orders, default=-1) + 1,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "archived_at": None,
            "groups": [],
            "tasks": [],
        }
        state["projects"].append(project)
        state["next_project_id"] += 1
        result["project_id"] = project["id"]

    state, result = _mutate(username, mutation)
    return _project_view(_find_project(state, result["project_id"]))


def update_project(username, project_id, changes):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None:
            return
        check_version(project, changes)
        for field in ("name", "objective", "materials", "due_date", "due_highlighted"):
            if field in changes:
                project[field] = changes[field]
        project["updated_at"] = _now()
        result["found"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return _project_view(project) if result.get("found") else None


def _material_payload(payload, *, partial=False, today=None):
    if not isinstance(payload, dict):
        raise ActionValidationError("请填写资料内容")
    fields = {}
    if not partial or "body" in payload:
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip() or len(body) > 20000:
            raise ActionValidationError("每条资料必须是 1–20000 字的文本")
        fields["body"] = body
    if not partial or "date" in payload:
        day = payload.get("date")
        if day is None and not partial:
            day = (today or datetime.now(timezone(timedelta(hours=8))).date()).isoformat()
        try:
            if not isinstance(day, str):
                raise ValueError
            fields["date"] = date.fromisoformat(day).isoformat()
        except ValueError as exc:
            raise ActionValidationError("记录日期请使用 YYYY-MM-DD") from exc
    for key in ("request_id", "expected_updated_at"):
        if key in payload:
            value = payload[key]
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ActionValidationError(f"{key} 必须是非空短文本")
            fields[key] = value
    return fields


def _append_material(project, payload, now, source_ref=None):
    entries = project.setdefault("material_entries", [])
    entry_id = max(project.get("next_material_entry_id", 1), _next_id(entries))
    entry = {"id": entry_id, "date": payload["date"], "body": payload["body"],
             "created_at": now, "updated_at": now}
    if source_ref:
        entry["source_ref"] = source_ref
    if payload.get("request_id"):
        entry.update(request_id=payload["request_id"], request_fingerprint=fingerprint(payload))
    entries.append(entry)
    project["next_material_entry_id"] = entry_id + 1
    project["updated_at"] = now
    return entry


def create_material_entry(username, project_id, payload, today=None):
    fields = _material_payload(payload, today=today)
    request_fields = {key: value for key, value in fields.items() if key != "date" or payload.get("date") is not None}
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None:
            return
        existing = replay(project.get("material_entries", []), request_fields)
        entry = existing or _append_material(project, fields, _now())
        if not existing and fields.get("request_id"):
            entry["request_fingerprint"] = fingerprint(request_fields)
        result["entry"] = copy.deepcopy(entry)
    _, result = _mutate(username, mutation)
    return result.get("entry")


def update_material_entry(username, project_id, entry_id, payload, *, delete=False):
    fields = _material_payload(payload, partial=True)
    if not fields.get("expected_updated_at"):
        raise ActionValidationError("修改资料请提供 expected_updated_at")
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None:
            return
        entries = project.get("material_entries", [])
        entry = next((item for item in entries if item["id"] == entry_id), None)
        if entry is None:
            return
        check_version(entry, fields)
        now = _now()
        if delete:
            project["material_entries"] = [item for item in entries if item["id"] != entry_id]
        else:
            entry.update({key: fields[key] for key in ("date", "body") if key in fields})
            entry["updated_at"] = now
        project["updated_at"] = now
        result["entry"] = copy.deepcopy(entry)
    _, result = _mutate(username, mutation)
    return result.get("entry")


def material_log(username, project_id=None):
    from material_log import parse_legacy_materials
    projects, entries = [], []
    for project in load_projects(username):
        if project_id is not None and project["id"] != project_id:
            continue
        projects.append({key: project[key] for key in ("id", "name", "status", "updated_at", "materials")})
        common = {"project_id": project["id"], "project_name": project["name"]}
        for entry in parse_legacy_materials(project["materials"]):
            entries.append({**entry, **common, "legacy": True, "created_at": None,
                            "updated_at": project["updated_at"]})
        for entry in project["material_entries"]:
            entries.append({**copy.deepcopy(entry), **common, "legacy": False})
    return {"projects": projects, "entries": entries}


def set_main_project(username, project_id):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        state["main_project_id"] = project_id
        result["found"] = True

    state, result = _mutate(username, mutation)
    return state["main_project_id"] if result.get("found") else None


def unset_main_project(username):
    def mutation(state, result):
        state["main_project_id"] = None
        result["found"] = True

    state, result = _mutate(username, mutation)
    return True


def _set_project_status(username, project_id, status):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None:
            return
        if status == "active" and project["status"] == "active":
            return
        if status != "active" and project["status"] != "active":
            return
        now = _now()
        project["status"] = status
        project["updated_at"] = now
        project["completed_at"] = now if status == "completed" else None
        project["archived_at"] = now if status == "archived" else None
        if status != "active" and state["main_project_id"] == project_id:
            state["main_project_id"] = None
        if status == "active":
            active_orders = [
                item["sort_order"]
                for item in state["projects"]
                if item["status"] == "active" and item["id"] != project_id
            ]
            project["sort_order"] = max(active_orders, default=-1) + 1
        result["found"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return (_project_view(project), state["main_project_id"]) if result.get("found") else (None, state["main_project_id"])


def complete_project(username, project_id):
    return _set_project_status(username, project_id, "completed")


def archive_project(username, project_id):
    return _set_project_status(username, project_id, "archived")


def reopen_project(username, project_id):
    return _set_project_status(username, project_id, "active")


def reorder_projects(username, project_ids):
    def mutation(state, result):
        active = [project for project in state["projects"] if project["status"] == "active" and not project.get("deleted_at")]
        if len(project_ids) != len(set(project_ids)) or {project["id"] for project in active} != set(project_ids):
            return
        by_id = {project["id"]: project for project in active}
        for order, project_id in enumerate(project_ids):
            by_id[project_id]["sort_order"] = order
            by_id[project_id]["updated_at"] = _now()
        result["valid"] = True

    state, result = _mutate(username, mutation)
    if not result.get("valid"):
        return None
    return [_project_view(project) for project in _ordered_projects(state) if project["status"] == "active"]


def set_last_viewed(username, project_id):
    def mutation(state, result):
        if _find_project(state, project_id) is None:
            return
        state["last_viewed_project_id"] = project_id
        result["found"] = True

    state, result = _mutate(username, mutation)
    return state["last_viewed_project_id"] if result.get("found") else None


def create_group(username, project_id, name):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        now = _now()
        group = {
            "id": _next_id(project["groups"]),
            "name": name,
            "sort_order": max((item["sort_order"] for item in project["groups"]), default=-1) + 1,
            "created_at": now,
            "updated_at": now,
        }
        project["groups"].append(group)
        project["updated_at"] = now
        result["group_id"] = group["id"]

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(_find_group(project, result["group_id"])) if result.get("group_id") else None


def update_group(username, project_id, group_id, name):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        group = _find_group(project, group_id) if project else None
        if group is None:
            return
        group["name"] = name
        group["updated_at"] = _now()
        project["updated_at"] = _now()
        result["found"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(_find_group(project, group_id)) if result.get("found") else None


def delete_group(username, project_id, group_id):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        group = _find_group(project, group_id) if project else None
        if group is None:
            return
        project["groups"] = [item for item in project["groups"] if item["id"] != group_id]
        ungrouped_order = max(
            (task["sort_order"] for task in project["tasks"] if task["group_id"] is None),
            default=-1,
        ) + 1
        for task in project["tasks"]:
            if task["group_id"] == group_id:
                task["group_id"] = None
                task["sort_order"] = ungrouped_order
                task["updated_at"] = _now()
                ungrouped_order += 1
        project["updated_at"] = _now()
        result["found"] = True

    _, result = _mutate(username, mutation)
    return bool(result.get("found"))


def reorder_groups(username, project_id, group_ids):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        if len(group_ids) != len(set(group_ids)) or {group["id"] for group in project["groups"]} != set(group_ids):
            return
        by_id = {group["id"]: group for group in project["groups"]}
        for order, group_id in enumerate(group_ids):
            by_id[group_id]["sort_order"] = order
            by_id[group_id]["updated_at"] = _now()
        project["groups"] = [by_id[group_id] for group_id in group_ids]
        project["updated_at"] = _now()
        result["valid"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(project["groups"]) if result.get("valid") else None


def create_task(username, project_id, payload):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        existing = replay(project["tasks"], payload)
        if existing:
            result["task_id"] = existing["id"]
            return
        group_id = payload.get("group_id")
        if group_id is not None and _find_group(project, group_id) is None:
            result["invalid_group"] = True
            return
        now = _now()
        task = {
            "id": project["next_task_id"],
            "name": payload["name"],
            "details": payload.get("details", ""),
            "commitment": payload.get("commitment", "growth"),
            "planned_on": payload.get("planned_on"),
            "estimate_minutes": payload.get("estimate_minutes"),
            "request_id": payload.get("request_id"),
            "request_fingerprint": fingerprint(payload),
            "group_id": group_id,
            "due_date": payload.get("due_date"),
            "done": False,
            "highlighted": bool(payload.get("highlighted", False)),
            "is_next_action": bool(payload.get("is_next_action", False)),
            "sort_order": max(
                (item["sort_order"] for item in project["tasks"] if item["group_id"] == group_id),
                default=-1,
            ) + 1,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        if task["is_next_action"]:
            for item in project["tasks"]:
                item["is_next_action"] = False
        project["tasks"].append(task)
        project["next_task_id"] += 1
        project["updated_at"] = now
        result["task_id"] = task["id"]

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(_find_task(project, result["task_id"], include_deleted=True)) if result.get("task_id") else None


def update_task(username, project_id, task_id, changes):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        task = _find_task(project, task_id) if project else None
        if task is None:
            return
        check_version(task, changes)
        if "name" in changes and changes["name"] != task["name"] and len(task["name"]) > 40:
            task.setdefault("original_name", task["name"])
            if not task.get("original_name"):
                task["original_name"] = task["name"]
        if changes.get("is_next_action") and task["done"]:
            result["invalid_next"] = True
            return
        if "group_id" in changes:
            group_id = changes["group_id"]
            if group_id is not None and _find_group(project, group_id) is None:
                result["invalid_group"] = True
                return
            if group_id != task["group_id"]:
                task["group_id"] = group_id
                task["sort_order"] = max(
                    (item["sort_order"] for item in project["tasks"] if item["id"] != task_id and item["group_id"] == group_id),
                    default=-1,
                ) + 1
        for field in ("name", "due_date", "highlighted", "details", "commitment", "planned_on", "estimate_minutes"):
            if field in changes:
                task[field] = changes[field]
        if "done" in changes:
            task["done"] = changes["done"]
            task["completed_at"] = _now() if changes["done"] else None
            if changes["done"]:
                task["is_next_action"] = False
        if changes.get("is_next_action"):
            for item in project["tasks"]:
                item["is_next_action"] = item["id"] == task_id
        elif "is_next_action" in changes:
            was_next = bool(task.get("is_next_action"))
            task["is_next_action"] = False
            if was_next and not task["done"]:
                replacement = _pick_default_next_task(project["groups"], project["tasks"], exclude_task_id=task_id)
                if replacement is not None:
                    replacement["is_next_action"] = True
                else:
                    task["is_next_action"] = True
        task["updated_at"] = _now()
        project["updated_at"] = _now()
        result["found"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(_find_task(project, task_id)) if result.get("found") else None


def set_next_task(username, project_id, task_id):
    return update_task(username, project_id, task_id, {"is_next_action": True})


def manage_record(username, project_id, operation, changes=None, task_id=None):
    """Delete (permanently) or preserve a task as materials in one locked update."""
    changes = changes or {}
    if operation not in {"delete", "restore", "to-materials"}:
        raise ActionValidationError("未知项目操作")
    def mutation(state, result):
        project = _find_project(state, project_id, include_deleted=True)
        if project is None or (task_id is not None and project.get("deleted_at")):
            return
        record = _find_task(project, task_id, include_deleted=True) if task_id is not None else project
        if record is None:
            if operation == "to-materials" and any(
                entry.get("source_ref") == f"project:{project_id}:{task_id}"
                for entry in project.get("material_entries", [])
            ):
                result["found"] = True
                result["view"] = _project_view(project)
            return
        check_version(record, changes)
        now = _now()
        if operation == "to-materials":
            if task_id is None:
                raise ActionValidationError("请选择要转为资料的任务")
            check_version(project, {"expected_updated_at": changes.get("expected_project_updated_at")})
            ref = f"project:{project_id}:{task_id}"
            text = f"### {record['name']}\n来源：{ref}\n{record.get('details') or ''}"
            if record.get("original_name"):
                text += f"\n原标题：{record['original_name']}"
            for key, label in (("planned_on", "原计划日期"), ("due_date", "原截止日期")):
                if record.get(key):
                    text += f"\n{label}：{record[key]}"
            payload = _material_payload({"body": text, "date": changes.get("material_date")})
            _append_material(project, payload, now, source_ref=ref)
            project["tasks"] = [t for t in project["tasks"] if t["id"] != task_id]
            project["updated_at"] = now
            result["found"] = True
            result["view"] = _project_view(project)
            return

        if operation == "delete":
            if task_id is not None:
                project["tasks"] = [t for t in project["tasks"] if t["id"] != task_id]
                project["updated_at"] = now
                result["found"] = True
                result["view"] = _project_view(project)
            else:
                deleted_view = _project_view(project)
                state["projects"] = [p for p in state["projects"] if p["id"] != project_id]
                if state.get("main_project_id") == project_id:
                    state["main_project_id"] = None
                if state.get("last_viewed_project_id") == project_id:
                    state["last_viewed_project_id"] = None
                state["updated_at"] = now
                result["found"] = True
                result["view"] = deleted_view
            return

        if operation == "restore":
            result["found"] = True
            result["view"] = _project_view(project)
            return

    state, result = _mutate(username, mutation)
    if not result.get("found"):
        return None
    return result.get("view")


def delete_task(username, project_id, task_id, changes=None):
    return bool(manage_record(username, project_id, "delete", changes, task_id))


def reorder_tasks(username, project_id, placements):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        ids = [placement.get("id") for placement in placements if isinstance(placement, dict)]
        if len(ids) != len(set(ids)) or {task["id"] for task in project["tasks"] if not task.get("deleted_at")} != set(ids):
            return
        valid_groups = {group["id"] for group in project["groups"]}
        if any(
            placement.get("group_id") is not None and placement.get("group_id") not in valid_groups
            for placement in placements
        ):
            return
        by_id = {task["id"]: task for task in project["tasks"]}
        orders = {}
        ordered = []
        for placement in placements:
            task = by_id[placement["id"]]
            group_id = placement.get("group_id")
            order = orders.get(group_id, 0)
            orders[group_id] = order + 1
            task["group_id"] = group_id
            task["sort_order"] = order
            task["updated_at"] = _now()
            ordered.append(task)
        project["tasks"] = ordered + [task for task in project["tasks"] if task.get("deleted_at")]
        project["updated_at"] = _now()
        result["valid"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy([task for task in project["tasks"] if not task.get("deleted_at")]) if result.get("valid") else None


def overview(username, today=None):
    state = load_state(username)
    active = [project for project in state["projects"] if project["status"] == "active" and not project.get("deleted_at")]
    main_id = state.get("main_project_id")

    def build_project_entry(proj, limit=5):
        value = _project_view(proj, today=today)
        group_names = {group["id"]: group["name"] for group in value["groups"]}
        pending = [task for task in value["tasks"] if not task["done"]]
        next_action = next((task for task in pending if task["is_next_action"]), None)
        remaining = [task for task in pending if next_action is None or task["id"] != next_action["id"]]

        def upcoming_key(task):
            due = task.get("due_date")
            if due:
                try:
                    due_day = date.fromisoformat(due)
                except ValueError:
                    due_day = date.max
                is_overdue = due_day < (today or date.today())
                return (0 if is_overdue else 1, due_day, task["sort_order"], task["id"])
            return (2, date.max, task["sort_order"], task["id"])

        def task_view(task):
            task = copy.deepcopy(task)
            task["group_name"] = group_names.get(task["group_id"])
            task["due_state"], task["due_days"] = _due_state(task.get("due_date"), today)
            return task

        upcoming = sorted(remaining, key=upcoming_key)
        parts = [p.strip() for p in value["name"].split("|", 1)]
        value["project_category"] = parts[0] if len(parts) > 1 and parts[0] else "项目"
        value["is_main"] = (proj["id"] == main_id)
        value["next_action"] = task_view(next_action) if next_action else None
        target = (today or datetime.now(timezone(timedelta(hours=8))).date()).isoformat()
        value["missed_plan_count"] = sum(bool(t.get("planned_on") and t["planned_on"] < target) for t in pending)
        value["due_today_count"] = sum(t.get("due_date") == target for t in pending) + int(value.get("due_date") == target)
        value["overdue_count"] = sum(bool(t.get("due_date") and t["due_date"] < target) for t in pending) + int(bool(value.get("due_date") and value["due_date"] < target))
        value["upcoming_tasks"] = [task_view(task) for task in upcoming[:limit]]
        value["hidden_task_count"] = max(0, len(upcoming) - limit)
        value.pop("groups", None)
        value.pop("tasks", None)
        value.pop("material_entries", None)
        value.pop("materials", None)
        return value

    active_projects = [build_project_entry(p, limit=2) for p in active]
    main = _find_project(state, main_id) if main_id is not None else None
    if main is None:
        main_entry = None
    else:
        main_entry = build_project_entry(main, limit=2)
        main_entry["is_main"] = True

    return {
        "main_project": main_entry,
        "active_projects": active_projects,
        "active_project_count": len(active),
    }


def _project_items(username):
    """All pending project records, independent of a view's visibility window."""
    items = []
    state = load_state(username)
    main_id = state.get("main_project_id")
    for project in load_projects(username):
        if project["status"] != "active":
            continue
        project_name = project["name"]
        is_main = (project["id"] == main_id)
        parts = [p.strip() for p in project_name.split("|", 1)]
        category = parts[0] if len(parts) > 1 and parts[0] else "项目"
        group_names = {group["id"]: group["name"] for group in project.get("groups", [])}

        if project.get("due_date"):
            items.append({
                "source": "Project",
                "id": f"due-{project['id']}",
                "kind": "project_due",
                "project_id": project["id"],
                "task_id": None,
                "title": f"完成项目：{project_name}",
                "calendar_title": f"项目截止 · {project_name}",
                "project_name": project_name,
                "project_category": category,
                "is_main": is_main,
                "is_next_action": False,
                "due_date": project["due_date"],
                "done": False,
                "flagged": bool(project.get("due_highlighted")),
                "uid": f"project-due-{project['id']}@canvas-dashboard",
            })
        for task in project["tasks"]:
            if task["done"]:
                continue
            items.append({
                "source": "Project",
                "id": f"task-{project['id']}-{task['id']}",
                "kind": "project_task",
                "project_id": project["id"],
                "task_id": task["id"],
                "title": task["name"],
                "details": task.get("details", ""),
                "commitment": task.get("commitment", "legacy"),
                "planned_on": task.get("planned_on"),
                "estimate_minutes": task.get("estimate_minutes"),
                "action_ref": f"project:{project['id']}:{task['id']}",
                "calendar_title": f"{task['name']} · {project_name}",
                "project_name": project_name,
                "project_category": category,
                "is_main": is_main,
                "is_next_action": bool(task.get("is_next_action")),
                "group_id": task.get("group_id"),
                "group_name": group_names.get(task.get("group_id")),
                "due_date": task["due_date"],
                "done": False,
                "flagged": bool(task.get("highlighted")),
                "uid": f"project-task-{project['id']}-{task['id']}@canvas-dashboard",
            })
    return items


def todo_items(username, today=None, scheduled_refs=None):
    target = (today or datetime.now(timezone(timedelta(hours=8))).date()).isoformat()
    scheduled_refs = set(scheduled_refs or ())
    result = []
    for item in _project_items(username):
        ref = item.get("action_ref") or f"project_due:{item['project_id']}"
        due, planned = item.get("due_date"), item.get("planned_on")
        missed = bool(planned and planned < target)
        is_today = bool((planned and planned <= target) or due == target or ref in scheduled_refs)
        if item["kind"] == "project_due" or is_today or (due and due < target):
            result.append({**item, "ref": ref, "action_ref": ref,
                           "is_today": is_today, "missed_plan": missed})
    return result


def calendar_items(username):
    """Calendar dates never depend on today's todo eligibility; UIDs stay stable."""
    items = []
    for item in _project_items(username):
        day = item.get("due_date") or item.get("planned_on")
        if day:
            if not item.get("due_date"):
                item["calendar_title"] = "计划 · " + item["calendar_title"]
            items.append({**item, "due_date": day})
    return items
