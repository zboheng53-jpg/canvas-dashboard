"""Bearer-authenticated workspace routes for external agents."""
import platform_sync
import project_store
import schedule_store
from datetime import date, datetime
from flask import Blueprint, abort, jsonify, request
from services.academic import get_term_info
from services.workspace import (
    _aggregate_agent_todos,
    _complete_agent_todo,
    _complete_schedule_occurrence,
    _create_custom_action,
    _manage_project_record,
    _project_focus,
    _project_payload,
    _project_task_payload,
    _project_trash,
    _recurring_occurrence_complete_response,
    _recurring_occurrence_skip_response,
    _recurring_occurrence_update_response,
    _recurring_todo_create_response,
    _recurring_todo_delete_response,
    _recurring_todo_detail_response,
    _recurring_todo_stop_response,
    _recurring_todo_update_response,
    _recurring_todos_list_response,
    _schedule_exception_response,
    _schedule_item_payload,
    _schedule_update_payload,
    _workspace_action_response,
    _workspace_actions_response,
    _workspace_agenda_response,
    _workspace_day,
)
from web_common import CST, api_error, invalid_request_response, read_json_request, require_agent_auth

bp = Blueprint("agent", __name__)


@bp.route("/api/agent/v1/schedule/recurring/<int:item_id>/exception", methods=["POST"])
@require_agent_auth
def api_agent_schedule_exception(item_id):
    return _schedule_exception_response(request.agent_username, item_id)


@bp.route("/api/agent/v1/schedule/<kind>/<int:item_id>/occurrence", methods=["PUT"])
@require_agent_auth
def api_agent_schedule_occurrence(kind, item_id):
    return _complete_schedule_occurrence(request.agent_username, kind, item_id)


@bp.route("/api/agent/v1/agenda")
@require_agent_auth
def api_agent_agenda():
    return _workspace_agenda_response(request.agent_username)


@bp.route("/api/agent/v1/actions")
@require_agent_auth
def api_agent_actions():
    return _workspace_actions_response(request.agent_username)


@bp.route("/api/agent/v1/actions/<path:ref>", methods=["GET", "PUT"])
@require_agent_auth
def api_agent_action(ref):
    return _workspace_action_response(request.agent_username, ref)


@bp.route("/api/agent/v1/projects/<int:project_id>/tasks", methods=["POST"])
@require_agent_auth
def api_agent_project_task_create(project_id):
    payload = _project_task_payload(read_json_request())
    if payload is None:
        return invalid_request_response()
    task = project_store.create_task(request.agent_username, project_id, payload)
    if task is None:
        return api_error("project_not_found", "项目或分组不存在", 404)
    return jsonify({"ok": True, "task": task, "ref": f"project:{project_id}:{task['id']}"}), 201


@bp.route("/api/agent/v1/projects/<int:project_id>", methods=["PUT"])
@require_agent_auth
def api_agent_project_update(project_id):
    changes = _project_payload(read_json_request(), partial=True)
    if not changes:
        return invalid_request_response()
    project = project_store.update_project(request.agent_username, project_id, changes)
    if project is None:
        return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "project": project})


@bp.route("/api/agent/v1/schedule/<kind>", methods=["POST"])
@require_agent_auth
def api_agent_schedule_create(kind):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    normalized = kind.replace("-", "_")
    payload = _schedule_item_payload(read_json_request(), normalized)
    if payload is None:
        return invalid_request_response()
    item = schedule_store.create_item(request.agent_username, normalized, payload)
    return jsonify({"ok": True, "item": item}), 201


@bp.route("/api/agent/v1/schedule/<kind>/<int:item_id>", methods=["PUT", "DELETE"])
@require_agent_auth
def api_agent_schedule_update(kind, item_id):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    normalized = kind.replace("-", "_")
    username = request.agent_username
    if request.method == "DELETE":
        return jsonify({"ok": schedule_store.delete_item(username, normalized, item_id)})
    payload = _schedule_update_payload(username, normalized, item_id, read_json_request())
    if payload is None:
        return invalid_request_response()
    item = schedule_store.update_item(username, normalized, item_id, payload)
    if item is None:
        return api_error("schedule_item_not_found", "日程不存在", 404)
    return jsonify({"ok": True, "item": item})


@bp.route("/api/agent/v1/ping")
@require_agent_auth
def api_agent_ping():
    return jsonify({
        "ok": True,
        "username": request.agent_username,
        "server_time": datetime.now(CST).isoformat(),
        "message": "Canvas Dashboard Agent API is active.",
    })


@bp.route("/api/agent/v1/schedule/today")
@require_agent_auth
def api_agent_schedule_today():
    username = request.agent_username
    today = datetime.now(CST).date()
    result = _workspace_day(username, today)
    return jsonify({"ok": True, **result})


@bp.route("/api/agent/v1/schedule/timetable")
@require_agent_auth
def api_agent_schedule_timetable():
    username = request.agent_username
    date_str = request.args.get("date", "").strip()
    term, _, semester_start = get_term_info()
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return api_error("invalid_date", "日期格式无效，请使用 YYYY-MM-DD", 400)
        result = _workspace_day(username, target_date)
        return jsonify({"ok": True, "date": target_date.isoformat(), **result})
    return jsonify({
        "ok": True,
        "term": term,
        "semester_start": semester_start,
        "courses": schedule_store.load_courses(username),
        "items": schedule_store.load_items(username),
    })


@bp.route("/api/agent/v1/todos", methods=["GET", "POST"])
@require_agent_auth
def api_agent_todos():
    username = request.agent_username
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        return jsonify({"ok": True, "todo": _create_custom_action(username, data)}), 201

    source = request.args.get("source", "all")
    status = request.args.get("status", "pending")
    todos = _aggregate_agent_todos(username, source=source, status=status)
    sync_meta = platform_sync.load(username).get("platforms", {})
    return jsonify({
        "ok": True,
        "todos": todos,
        "count": len(todos),
        "sync_status": sync_meta,
    })


@bp.route("/api/agent/v1/todos/<path:todo_id>/complete", methods=["POST"])
@require_agent_auth
def api_agent_todo_complete(todo_id):
    username = request.agent_username
    data = read_json_request() or {}
    source = data.get("source") or request.args.get("source")
    if not source:
        if str(todo_id).startswith("recurring_"):
            source = "recurring"
        elif str(todo_id).startswith("task-") or str(todo_id).startswith("due-"):
            source = "project"
        elif ":" in str(todo_id):
            source = "custom_subtask"
        else:
            source = "custom"
    success = _complete_agent_todo(username, todo_id, source=source)
    if not success:
        return api_error("todo_not_found", "未找到指定待办或无法标记完成", 404)
    return jsonify({"ok": True, "id": todo_id, "source": source, "completed": True})


@bp.route("/api/agent/v1/recurring-todos", methods=["GET", "POST"])
@require_agent_auth
def api_agent_recurring_todos():
    if request.method == "POST":
        return _recurring_todo_create_response(request.agent_username)
    return _recurring_todos_list_response(request.agent_username)


@bp.route("/api/agent/v1/recurring-todos/<int:series_id>", methods=["GET", "PUT", "DELETE"])
@require_agent_auth
def api_agent_recurring_todo_item(series_id):
    username = request.agent_username
    if request.method == "DELETE":
        return _recurring_todo_delete_response(username, series_id)
    if request.method == "PUT":
        return _recurring_todo_update_response(username, series_id)
    return _recurring_todo_detail_response(username, series_id)


@bp.route("/api/agent/v1/recurring-todos/<int:series_id>/stop", methods=["POST"])
@require_agent_auth
def api_agent_recurring_todo_stop(series_id):
    return _recurring_todo_stop_response(request.agent_username, series_id)


@bp.route("/api/agent/v1/recurring-todos/<int:series_id>/occurrences/<date_str>/complete", methods=["PUT"])
@require_agent_auth
def api_agent_recurring_occurrence_complete(series_id, date_str):
    return _recurring_occurrence_complete_response(request.agent_username, series_id, date_str)


@bp.route("/api/agent/v1/recurring-todos/<int:series_id>/occurrences/<date_str>/skip", methods=["PUT"])
@require_agent_auth
def api_agent_recurring_occurrence_skip(series_id, date_str):
    return _recurring_occurrence_skip_response(request.agent_username, series_id, date_str)


@bp.route("/api/agent/v1/recurring-todos/<int:series_id>/occurrences/<date_str>", methods=["PUT"])
@require_agent_auth
def api_agent_recurring_occurrence_update(series_id, date_str):
    return _recurring_occurrence_update_response(request.agent_username, series_id, date_str)


@bp.route("/api/agent/v1/projects/trash")
@require_agent_auth
def api_agent_project_trash():
    return _project_trash(request.agent_username)


@bp.route("/api/agent/v1/projects/<int:project_id>/<operation>", methods=["POST"])
@require_agent_auth
def api_agent_project_manage(project_id, operation):
    if operation not in {"delete", "restore"}:
        abort(404)
    return _manage_project_record(request.agent_username, project_id, operation)


@bp.route("/api/agent/v1/projects/<int:project_id>/tasks/<int:task_id>/<operation>", methods=["POST"])
@require_agent_auth
def api_agent_project_task_manage(project_id, task_id, operation):
    if operation not in {"delete", "restore", "to-materials"}:
        abort(404)
    return _manage_project_record(request.agent_username, project_id, operation, task_id)


@bp.route("/api/agent/v1/actions/focus")
@require_agent_auth
def api_agent_project_focus():
    return _project_focus(request.agent_username)


@bp.route("/api/agent/v1/projects")
@require_agent_auth
def api_agent_projects():
    username = request.agent_username
    state = project_store.load_state(username)
    return jsonify({
        "ok": True,
        "primary_project_id": state.get("main_project_id"),
        "main_project_id": state.get("main_project_id"),
        "projects": project_store.load_projects(username),
        "overview": project_store.overview(username),
    })


@bp.route("/api/agent/v1/sync/status")
@require_agent_auth
def api_agent_sync_status():
    username = request.agent_username
    return jsonify({
        "ok": True,
        "statuses": platform_sync.load(username)["platforms"],
    })

