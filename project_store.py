"""Atomic per-user storage for Dashboard V2 long-term projects."""
from datetime import datetime, timezone

from storage import locked_json_update, read_json_file
import user_paths


def _file(username):
    return user_paths.user_dir(username) / "projects.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_projects(username):
    data = read_json_file(_file(username), [])
    return data if isinstance(data, list) else []


def _next_id(values):
    return max((int(value.get("id", 0)) for value in values if str(value.get("id", "")).isdigit()), default=0) + 1


def create_project(username, payload):
    created = {}
    def update(projects):
        project = {"id": _next_id(projects), "name": payload["name"], "progress": payload.get("progress", 0), "due_date": payload.get("due_date"), "next_action": payload.get("next_action", ""), "status": "active", "goals": [], "created_at": _now(), "updated_at": _now()}
        projects.append(project); created.update(project); return projects
    locked_json_update(_file(username), [], update)
    return created


def update_project(username, project_id, changes):
    result = {}
    def update(projects):
        for project in projects:
            if project.get("id") == project_id:
                project.update(changes); project["updated_at"] = _now(); result.update(project); break
        return projects
    locked_json_update(_file(username), [], update)
    return result or None


def create_goal(username, project_id, text):
    result = {}
    def update(projects):
        for project in projects:
            if project.get("id") == project_id:
                goals = project.setdefault("goals", []); goal = {"id": _next_id(goals), "text": text, "done": False}; goals.append(goal); project["updated_at"] = _now(); result.update(goal); break
        return projects
    locked_json_update(_file(username), [], update)
    return result or None


def update_goal(username, project_id, goal_id, changes):
    result = {}
    def update(projects):
        for project in projects:
            if project.get("id") == project_id:
                for goal in project.get("goals", []):
                    if goal.get("id") == goal_id:
                        goal.update(changes); project["updated_at"] = _now(); result.update(goal); break
        return projects
    locked_json_update(_file(username), [], update)
    return result or None


def delete_goal(username, project_id, goal_id):
    deleted = {"value": False}
    def update(projects):
        for project in projects:
            if project.get("id") == project_id:
                goals = project.get("goals", []); project["goals"] = [goal for goal in goals if goal.get("id") != goal_id]; deleted["value"] = len(goals) != len(project["goals"]); project["updated_at"] = _now(); break
        return projects
    locked_json_update(_file(username), [], update)
    return deleted["value"]


def reorder_goals(username, project_id, goal_ids):
    result = {}
    def update(projects):
        for project in projects:
            if project.get("id") == project_id:
                goals = {goal.get("id"): goal for goal in project.get("goals", [])}
                if set(goals) != set(goal_ids): break
                project["goals"] = [goals[goal_id] for goal_id in goal_ids]; project["updated_at"] = _now(); result["goals"] = project["goals"]; break
        return projects
    locked_json_update(_file(username), [], update)
    return result.get("goals")
