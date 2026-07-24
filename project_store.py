"""Atomic per-user storage for long-term projects, groups, and tasks."""
import copy
from datetime import date, datetime, timezone

from storage import locked_json_update, read_json_file
import user_paths


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
        "name": str(name or "未命名任务")[:160],
        "group_id": group_id,
        "due_date": task.get("due_date") or None,
        "done": done,
        "highlighted": bool(task.get("highlighted", False)),
        "is_next_action": bool(task.get("is_next_action", False)) and not done,
        "sort_order": _int(task.get("sort_order"), fallback_order),
        "created_at": task.get("created_at") or now,
        "updated_at": task.get("updated_at") or task.get("created_at") or now,
        "completed_at": (task.get("completed_at") or now) if done else None,
    }


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
        if task["id"] in used_task_ids:
            task["id"] = max(used_task_ids, default=0) + 1
        used_task_ids.add(task["id"])
        if task["is_next_action"]:
            if next_action_seen:
                task["is_next_action"] = False
            next_action_seen = True
        tasks.append(task)

    status = project.get("status")
    if status not in PROJECT_STATUSES:
        status = "active"
    completed_at = project.get("completed_at") if status == "completed" else None
    archived_at = project.get("archived_at") if status == "archived" else None
    if status == "completed" and not completed_at:
        completed_at = project.get("updated_at") or now
    if status == "archived" and not archived_at:
        archived_at = project.get("updated_at") or now
    return {
        "id": _int(project.get("id"), fallback_id),
        "name": str(project.get("name") or "未命名项目")[:100],
        "objective": str(project.get("objective") or "")[:240],
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
        if project["id"] in used_ids:
            project["id"] = max(used_ids, default=0) + 1
        used_ids.add(project["id"])
        projects.append(project)
    active_ids = {project["id"] for project in projects if project["status"] == "active"}
    all_ids = {project["id"] for project in projects}
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


def _project_view(project, today=None):
    value = copy.deepcopy(project)
    value["groups"].sort(key=lambda group: (group["sort_order"], group["id"]))
    value["tasks"].sort(key=lambda task: (task["sort_order"], task["id"]))
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


def load_projects(username):
    state = load_state(username)
    return [_project_view(project) for project in _ordered_projects(state)]


def _mutate(username, mutator):
    result = {}

    def update(raw):
        state = _normalize_state(raw)
        mutator(state, result)
        return _normalize_state(state)

    state = locked_json_update(_file(username), _empty_state(), update)
    return state, result


def _find_project(state, project_id):
    return next((project for project in state["projects"] if project["id"] == project_id), None)


def _find_group(project, group_id):
    return next((group for group in project["groups"] if group["id"] == group_id), None)


def _find_task(project, task_id):
    return next((task for task in project["tasks"] if task["id"] == task_id), None)


def create_project(username, payload):
    def mutation(state, result):
        now = _now()
        active_orders = [project["sort_order"] for project in state["projects"] if project["status"] == "active"]
        project = {
            "id": _next_id(state["projects"]),
            "name": payload["name"],
            "objective": payload.get("objective", ""),
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
        result["project_id"] = project["id"]

    state, result = _mutate(username, mutation)
    return _project_view(_find_project(state, result["project_id"]))


def update_project(username, project_id, changes):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None:
            return
        for field in ("name", "objective", "due_date", "due_highlighted"):
            if field in changes:
                project[field] = changes[field]
        project["updated_at"] = _now()
        result["found"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return _project_view(project) if result.get("found") else None


def set_main_project(username, project_id):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        state["main_project_id"] = project_id
        result["found"] = True

    state, result = _mutate(username, mutation)
    return state["main_project_id"] if result.get("found") else None


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
        active = [project for project in state["projects"] if project["status"] == "active"]
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
        group_id = payload.get("group_id")
        if group_id is not None and _find_group(project, group_id) is None:
            result["invalid_group"] = True
            return
        now = _now()
        task = {
            "id": _next_id(project["tasks"]),
            "name": payload["name"],
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
        project["updated_at"] = now
        result["task_id"] = task["id"]

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(_find_task(project, result["task_id"])) if result.get("task_id") else None


def update_task(username, project_id, task_id, changes):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        task = _find_task(project, task_id) if project else None
        if task is None:
            return
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
        for field in ("name", "due_date", "highlighted"):
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
            task["is_next_action"] = False
        task["updated_at"] = _now()
        project["updated_at"] = _now()
        result["found"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(_find_task(project, task_id)) if result.get("found") else None


def set_next_task(username, project_id, task_id):
    return update_task(username, project_id, task_id, {"is_next_action": True})


def delete_task(username, project_id, task_id):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        task = _find_task(project, task_id) if project else None
        if task is None:
            return
        project["tasks"] = [item for item in project["tasks"] if item["id"] != task_id]
        project["updated_at"] = _now()
        result["found"] = True

    _, result = _mutate(username, mutation)
    return bool(result.get("found"))


def reorder_tasks(username, project_id, placements):
    def mutation(state, result):
        project = _find_project(state, project_id)
        if project is None or project["status"] != "active":
            return
        ids = [placement.get("id") for placement in placements if isinstance(placement, dict)]
        if len(ids) != len(set(ids)) or {task["id"] for task in project["tasks"]} != set(ids):
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
        project["tasks"] = ordered
        project["updated_at"] = _now()
        result["valid"] = True

    state, result = _mutate(username, mutation)
    project = _find_project(state, project_id)
    return copy.deepcopy(project["tasks"]) if result.get("valid") else None


def overview(username, today=None):
    state = load_state(username)
    active = [project for project in state["projects"] if project["status"] == "active"]
    main = _find_project(state, state["main_project_id"]) if state["main_project_id"] is not None else None
    if main is None:
        return {"main_project": None, "active_project_count": len(active)}
    value = _project_view(main, today=today)
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
    value["next_action"] = task_view(next_action) if next_action else None
    value["upcoming_tasks"] = [task_view(task) for task in upcoming[:2]]
    value["hidden_task_count"] = max(0, len(upcoming) - 2)
    value.pop("groups", None)
    value.pop("tasks", None)
    return {"main_project": value, "active_project_count": len(active)}


def todo_items(username):
    items = []
    for project in load_projects(username):
        if project["status"] != "active":
            continue
        project_name = project["name"]
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
                "due_date": project["due_date"],
                "done": False,
                "flagged": bool(project.get("due_highlighted")),
                "uid": f"project-due-{project['id']}@canvas-dashboard",
            })
        for task in project["tasks"]:
            if task["done"] or not task.get("due_date"):
                continue
            items.append({
                "source": "Project",
                "id": f"task-{project['id']}-{task['id']}",
                "kind": "project_task",
                "project_id": project["id"],
                "task_id": task["id"],
                "title": task["name"],
                "calendar_title": f"{task['name']} · {project_name}",
                "project_name": project_name,
                "group_id": task.get("group_id"),
                "due_date": task["due_date"],
                "done": False,
                "flagged": bool(task.get("highlighted")),
                "uid": f"project-task-{project['id']}-{task['id']}@canvas-dashboard",
            })
    return items
