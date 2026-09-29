"""Browser routes for todos, projects, schedules and the unified workspace."""
import logging
import project_store
import recurring_todo_store
import schedule_store
import tongji_login_sessions
import tongji_timetable
from action_contract import action_fields, check_version, short_title
from datetime import datetime
from flask import Blueprint, abort, jsonify, redirect, request, session
from login_capacity import LoginCapacityError
from services.academic import get_term_info
from services.workspace import (
    _complete_schedule_occurrence,
    _create_custom_action,
    _custom_action_ref,
    _manage_project_record,
    _normalize_todos,
    _project_focus,
    _project_group_name,
    _project_payload,
    _project_status_response,
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
    _remove_expired_completed_todos,
    _schedule_exception_response,
    _schedule_item_payload,
    _schedule_overlap,
    _schedule_update_payload,
    _todo_timestamp,
    _todos_file,
    _workspace_action_response,
    _workspace_actions_response,
    _workspace_agenda_response,
    _workspace_day,
)
from storage import locked_json_update
from web_common import CST, api_error, invalid_request_response, read_json_request

logger = logging.getLogger(__name__)
bp = Blueprint("planning", __name__)


@bp.route("/api/custom/todos", methods=["GET", "POST"])
def api_custom_todos():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        return jsonify({"ok": True, "todo": _create_custom_action(username, data)})

    today = datetime.now(CST).date()
    todos = _remove_expired_completed_todos(username, today)

    for r_item in recurring_todo_store.get_homepage_items(username, today=today):
        todos.append({
            "id": r_item["id"],
            "raw_id": r_item["id"],
            "text": r_item["title"],
            "details": r_item.get("details", ""),
            "due_date": r_item["due_date"],
            "done": r_item["done"],
            "skipped": r_item.get("skipped", False),
            "is_recurring": True,
            "series_id": r_item["series_id"],
            "original_due_date": r_item["original_due_date"],
            "interval_weeks": r_item["interval_weeks"],
            "repeat_label": r_item["repeat_label"],
            "labels": [f"↻ {r_item['repeat_label']}"],
            "commitment": "obligation",
            "source": "custom",
            "created_at": r_item.get("series_created_at"),
            "ref": r_item["action_ref"],
        })

    todos.sort(key=lambda t: (
        1 if t["done"] else 0,
        0 if t.get("due_date") else 1,
        t.get("due_date") or "9999-99-99",
    ))
    return jsonify({"ok": True, "data": [{**t, "ref": t.get("ref") or _custom_action_ref(t)} for t in todos], "today": datetime.now(CST).strftime("%Y-%m-%d")})


@bp.route("/api/custom/todos/<int:todo_id>", methods=["PUT", "DELETE"])
def api_custom_todo_item(todo_id):
    username = session["username"]
    if request.method == "DELETE":
        locked_json_update(
            _todos_file(username),
            [],
            lambda todos: [t for t in _normalize_todos(todos) if t["id"] != todo_id],
        )
        return jsonify({"ok": True})

    if request.method == "PUT":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        fields = action_fields(data)
        if "text" in data:
            fields["text"] = short_title(data["text"])
        result = {"conflict": False, "todo": None}

        def update_todos(current):
            current = _normalize_todos(current)
            for t in current:
                if t["id"] == todo_id:
                    check_version(t, fields)
                    if (
                        "subtasks" in data
                        and data.get("updated_at")
                        and data.get("updated_at") != t.get("updated_at")
                    ):
                        result["conflict"] = True
                        result["todo"] = dict(t)
                        break
                    if "done" in data:
                        t["done"] = data["done"]
                        t["completed_at"] = _todo_timestamp() if data["done"] else None
                    if "text" in data:
                        t["text"] = data["text"]
                    if "due_date" in data:
                        t["due_date"] = (data["due_date"] or "").strip() or None
                    if "highlighted" in data:
                        t["highlighted"] = data["highlighted"]
                    if "labels" in data:
                        t["labels"] = data["labels"]
                    if "subtasks" in data:
                        t["subtasks"] = data["subtasks"]
                    t.update({k: v for k, v in fields.items() if k not in ("expected_updated_at", "request_id")})
                    t["updated_at"] = _todo_timestamp()
                    result["todo"] = dict(t)
                    break
            return current

        locked_json_update(_todos_file(username), [], update_todos)
        if result["conflict"]:
            return jsonify({
                "ok": False,
                "code": "custom_todo_conflict",
                "error": "Todo changed; refresh and try again",
                "todo": result["todo"],
            }), 409
        return jsonify({"ok": True, "todo": result["todo"]})

    return jsonify({"ok": False, "error": "Method not allowed"}), 405


@bp.route("/api/recurring-todos", methods=["GET", "POST"])
def api_recurring_todos():
    if request.method == "POST":
        return _recurring_todo_create_response(session["username"])
    return _recurring_todos_list_response(session["username"])


@bp.route("/api/recurring-todos/<int:series_id>", methods=["GET", "PUT", "DELETE"])
def api_recurring_todo_item(series_id):
    username = session["username"]
    if request.method == "DELETE":
        return _recurring_todo_delete_response(username, series_id)
    if request.method == "PUT":
        return _recurring_todo_update_response(username, series_id)
    return _recurring_todo_detail_response(username, series_id)


@bp.route("/api/recurring-todos/<int:series_id>/stop", methods=["POST"])
def api_recurring_todo_stop(series_id):
    return _recurring_todo_stop_response(session["username"], series_id)


@bp.route("/api/recurring-todos/<int:series_id>/occurrences/<date_str>/complete", methods=["PUT"])
def api_recurring_occurrence_complete(series_id, date_str):
    return _recurring_occurrence_complete_response(session["username"], series_id, date_str)


@bp.route("/api/recurring-todos/<int:series_id>/occurrences/<date_str>/skip", methods=["PUT"])
def api_recurring_occurrence_skip(series_id, date_str):
    return _recurring_occurrence_skip_response(session["username"], series_id, date_str)


@bp.route("/api/recurring-todos/<int:series_id>/occurrences/<date_str>", methods=["PUT"])
def api_recurring_occurrence_update(series_id, date_str):
    return _recurring_occurrence_update_response(session["username"], series_id, date_str)


@bp.route("/api/schedule", methods=["GET"])
def api_schedule():
    username = session["username"]
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username), "items": schedule_store.load_items(username)})


@bp.route("/api/schedule/refresh", methods=["POST"])
def api_schedule_refresh():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    tongji_username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not tongji_username or not password:
        return api_error("timetable_credentials_required", "请输入统一身份认证账号和密码")
    try:
        courses = tongji_timetable.fetch_selected_courses_with_credentials(tongji_username, password)
    except tongji_timetable.TimetableLoginError as exc:
        return api_error("timetable_login_failed", str(exc), 401)
    except tongji_timetable.TimetableFetchError as exc:
        return api_error("timetable_fetch_failed", str(exc), 502)
    term, _, semester_start = get_term_info()
    schedule_store.save_courses(username, term, semester_start, courses, datetime.now(CST).isoformat())
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username)})


@bp.route("/api/schedule/login-session", methods=["POST"])
def api_schedule_login_session():
    username = session["username"]
    try:
        login_session = tongji_login_sessions.create_session(username)
    except LoginCapacityError as exc:
        return jsonify({"ok": False, "code": "login_capacity", "error": str(exc)}), 429, {"Retry-After": "30"}
    except Exception as exc:
        logger.exception("Failed to create Tongji login session")
        return api_error("timetable_login_session_failed", f"无法打开认证窗口：{exc}", 500)
    return jsonify({
        "ok": True,
        "token": login_session["token"],
        "url": login_session["url"],
        "expires_at": login_session["expires_at"],
    })


@bp.route("/schedule/session/<token>/")
def schedule_login_session_page(token):
    login_session = tongji_login_sessions.session_for_token(token)
    if not login_session or login_session.get("username") != session.get("username"):
        return "Not Found", 404
    port = login_session["port"]
    if not tongji_login_sessions.validate_session(token, port):
        return "Not Found", 404
    vnc_path = f"tji-vnc/{port}/{token}/websockify"
    return redirect(f"/tji-vnc/{port}/{token}/vnc.html?autoconnect=true&resize=scale&path={vnc_path}")


@bp.route("/api/schedule/login-session-auth")
def api_schedule_login_session_auth():
    token = request.args.get("token", "") or request.headers.get("X-Tongji-Token", "")
    port = request.args.get("port", "") or request.headers.get("X-Tongji-Port", "")
    login_session = tongji_login_sessions.session_for_token(token)
    if not tongji_login_sessions.validate_session(token, port) or not login_session:
        return "", 401
    if login_session.get("username") != session.get("username"):
        return "", 401
    return "", 204


@bp.route("/api/schedule/login-session/<token>/complete", methods=["POST"])
def api_schedule_login_session_complete(token):
    username = session["username"]
    login_session = tongji_login_sessions.session_for_token(token)
    if not login_session or login_session.get("username") != username:
        return api_error("timetable_login_session_missing", "认证窗口不存在或已过期", 404)
    try:
        courses = tongji_timetable.fetch_selected_courses_from_cdp(
            f"http://127.0.0.1:{login_session['debug_port']}"
        )
    except tongji_timetable.TimetableFetchError as exc:
        return api_error("timetable_fetch_failed", str(exc), 400)
    tongji_login_sessions.stop_session(username, token)
    term, _, semester_start = get_term_info()
    schedule_store.save_courses(username, term, semester_start, courses, datetime.now(CST).isoformat())
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username)})


@bp.route("/api/schedule/login-session/<token>", methods=["DELETE"])
def api_schedule_login_session_stop(token):
    return jsonify({"ok": tongji_login_sessions.stop_session(session["username"], token)})


@bp.route("/api/schedule/import", methods=["POST"])
def api_schedule_import():
    uploaded = request.files.get("course_file")
    if uploaded is None or not uploaded.filename:
        return api_error("timetable_file_missing", "请选择课表插件导出的 .xlsx 文件")
    if not uploaded.filename.lower().endswith(".xlsx"):
        return api_error("timetable_file_invalid", "仅支持课表插件导出的 .xlsx 文件")
    try:
        courses = tongji_timetable.parse_exported_timetable_xlsx(uploaded.read())
    except ValueError as error:
        return api_error("timetable_file_invalid", str(error))
    username = session["username"]
    term, _, semester_start = get_term_info()
    schedule_store.save_courses(username, term, semester_start, courses, datetime.now(CST).isoformat())
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username)})


@bp.route("/api/schedule/courses", methods=["DELETE"])
def api_schedule_courses_clear():
    username = session["username"]
    schedule_store.clear_courses(username)
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username)})


@bp.route("/api/schedule/courses/<path:course_id>", methods=["DELETE"])
def api_schedule_course_delete(course_id):
    username = session["username"]
    found = schedule_store.delete_course(username, course_id)
    if not found:
        return api_error("course_not_found", "未找到指定课程", 404)
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username)})


@bp.route("/api/schedule/<kind>", methods=["POST"])
def api_schedule_item_create(kind):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    username = session["username"]
    payload = _schedule_item_payload(read_json_request(), "recurring" if kind == "recurring" else "one_off")
    if payload is None:
        return invalid_request_response()
    item = schedule_store.create_item(username, "recurring" if kind == "recurring" else "one_off", payload)
    return jsonify({"ok": True, "item": item, "overlap": _schedule_overlap(username, "recurring" if kind == "recurring" else "one_off", payload, item["id"])})


@bp.route("/api/schedule/<kind>/<int:item_id>", methods=["PUT", "DELETE"])
def api_schedule_item(kind, item_id):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    username = session["username"]
    normalized_kind = "recurring" if kind == "recurring" else "one_off"
    if request.method == "DELETE":
        return jsonify({"ok": schedule_store.delete_item(username, normalized_kind, item_id)})
    payload = _schedule_update_payload(username, normalized_kind, item_id, read_json_request())
    if payload is None:
        return invalid_request_response()
    item = schedule_store.update_item(username, normalized_kind, item_id, payload)
    if item is None:
        return api_error("schedule_item_not_found", "日程不存在", 404)
    return jsonify({"ok": True, "item": item, "overlap": _schedule_overlap(username, normalized_kind, payload, item_id)})


@bp.route("/api/schedule/today")
def api_schedule_today():
    username = session["username"]
    today = datetime.now(CST).date()
    result = _workspace_day(username, today)
    return jsonify({"ok": True, **result})


@bp.route("/api/projects", methods=["GET", "POST"])
def api_projects():
    username = session["username"]
    if request.method == "POST":
        payload = _project_payload(read_json_request())
        if payload is None:
            return invalid_request_response()
        return jsonify({"ok": True, "project": project_store.create_project(username, payload)})
    state = project_store.load_state(username)
    return jsonify({
        "ok": True,
        "projects": project_store.load_projects(username),
        "main_project_id": state["main_project_id"],
        "last_viewed_project_id": state["last_viewed_project_id"],
    })


@bp.route("/api/projects/overview")
def api_projects_overview():
    return jsonify({
        "ok": True,
        **project_store.overview(session["username"], today=datetime.now(CST).date()),
    })


@bp.route("/api/projects/todos")
def api_project_todos():
    items = project_store.todo_items(session["username"])
    items.sort(key=lambda item: (item.get("due_date") or "9999-12-31", item["project_id"], item["id"]))
    return jsonify({"ok": True, "items": items, "count": len(items)})


@bp.route("/api/projects/<int:project_id>", methods=["PUT", "DELETE"])
def api_project(project_id):
    if request.method == "DELETE":
        return _manage_project_record(session["username"], project_id, "delete")
    payload = _project_payload(read_json_request(), partial=True)
    if payload is None or not payload:
        return invalid_request_response()
    project = project_store.update_project(session["username"], project_id, payload)
    if project is None:
        return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "project": project})


@bp.route("/api/projects/<int:project_id>/set-main", methods=["POST"])
def api_project_set_main(project_id):
    main_project_id = project_store.set_main_project(session["username"], project_id)
    if main_project_id is None:
        return api_error("project_not_active", "只能将进行中的项目置顶", 400)
    return jsonify({"ok": True, "main_project_id": main_project_id})


@bp.route("/api/projects/unset-main", methods=["POST"])
@bp.route("/api/projects/<int:project_id>/unset-main", methods=["POST"])
def api_project_unset_main(project_id=None):
    project_store.unset_main_project(session["username"])
    return jsonify({"ok": True, "main_project_id": None})


@bp.route("/api/projects/<int:project_id>/complete", methods=["POST"])
def api_project_complete(project_id):
    return _project_status_response(project_id, project_store.complete_project)


@bp.route("/api/projects/<int:project_id>/archive", methods=["POST"])
def api_project_archive(project_id):
    return _project_status_response(project_id, project_store.archive_project)


@bp.route("/api/projects/<int:project_id>/reopen", methods=["POST"])
def api_project_reopen(project_id):
    return _project_status_response(project_id, project_store.reopen_project)


@bp.route("/api/projects/reorder", methods=["POST"])
def api_projects_reorder():
    data = read_json_request()
    project_ids = data.get("project_ids") if data else None
    if (
        not isinstance(project_ids, list)
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in project_ids)
    ):
        return invalid_request_response()
    projects = project_store.reorder_projects(session["username"], project_ids)
    if projects is None:
        return api_error("project_order_invalid", "项目顺序无效", 400)
    return jsonify({"ok": True, "projects": projects})


@bp.route("/api/projects/<int:project_id>/viewed", methods=["POST"])
def api_project_viewed(project_id):
    viewed_id = project_store.set_last_viewed(session["username"], project_id)
    if viewed_id is None:
        return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "last_viewed_project_id": viewed_id})


@bp.route("/api/projects/<int:project_id>/groups", methods=["POST"])
def api_project_group_create(project_id):
    name = _project_group_name(read_json_request())
    if name is None:
        return invalid_request_response()
    group = project_store.create_group(session["username"], project_id, name)
    if group is None:
        return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "group": group})


@bp.route("/api/projects/<int:project_id>/groups/<int:group_id>", methods=["PUT", "DELETE"])
def api_project_group(project_id, group_id):
    if request.method == "DELETE":
        if not project_store.delete_group(session["username"], project_id, group_id):
            return api_error("group_not_found", "分组不存在", 404)
        return jsonify({"ok": True})
    name = _project_group_name(read_json_request())
    if name is None:
        return invalid_request_response()
    group = project_store.update_group(session["username"], project_id, group_id, name)
    if group is None:
        return api_error("group_not_found", "分组不存在", 404)
    return jsonify({"ok": True, "group": group})


@bp.route("/api/projects/<int:project_id>/groups/reorder", methods=["POST"])
def api_project_groups_reorder(project_id):
    data = read_json_request()
    group_ids = data.get("group_ids") if data else None
    if (
        not isinstance(group_ids, list)
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in group_ids)
    ):
        return invalid_request_response()
    groups = project_store.reorder_groups(session["username"], project_id, group_ids)
    if groups is None:
        return api_error("group_order_invalid", "分组顺序无效", 400)
    return jsonify({"ok": True, "groups": groups})


@bp.route("/api/projects/<int:project_id>/tasks", methods=["POST"])
def api_project_task_create(project_id):
    payload = _project_task_payload(read_json_request())
    if payload is None:
        return invalid_request_response()
    task = project_store.create_task(session["username"], project_id, payload)
    if task is None:
        return api_error("project_or_group_not_found", "项目或分组不存在", 404)
    return jsonify({"ok": True, "task": task})


@bp.route("/api/projects/<int:project_id>/tasks/<int:task_id>", methods=["PUT", "DELETE"])
def api_project_task(project_id, task_id):
    if request.method == "DELETE":
        if not project_store.delete_task(session["username"], project_id, task_id, read_json_request() or {}):
            return api_error("task_not_found", "任务不存在", 404)
        return jsonify({"ok": True})
    payload = _project_task_payload(read_json_request(), partial=True)
    if payload is None or not payload:
        return invalid_request_response()
    task = project_store.update_task(session["username"], project_id, task_id, payload)
    if task is None:
        return api_error("task_update_invalid", "任务不存在或分组无效", 400)
    return jsonify({"ok": True, "task": task})


@bp.route("/api/projects/<int:project_id>/tasks/<int:task_id>/set-next", methods=["POST"])
def api_project_task_set_next(project_id, task_id):
    task = project_store.set_next_task(session["username"], project_id, task_id)
    if task is None:
        return api_error("next_action_invalid", "只能选择进行中项目的未完成任务", 400)
    return jsonify({"ok": True, "task": task})


@bp.route("/api/projects/<int:project_id>/tasks/reorder", methods=["POST"])
def api_project_tasks_reorder(project_id):
    data = read_json_request()
    placements = data.get("tasks") if data else None
    if not isinstance(placements, list) or not all(isinstance(item, dict) for item in placements):
        return invalid_request_response()
    for item in placements:
        task_id = item.get("id")
        group_id = item.get("group_id")
        if (
            not isinstance(task_id, int)
            or isinstance(task_id, bool)
            or task_id < 1
            or (
                group_id is not None
                and (not isinstance(group_id, int) or isinstance(group_id, bool) or group_id < 1)
            )
        ):
            return invalid_request_response()
    tasks = project_store.reorder_tasks(session["username"], project_id, placements)
    if tasks is None:
        return api_error("task_order_invalid", "任务顺序无效", 400)
    return jsonify({"ok": True, "tasks": tasks})


@bp.route("/api/schedule/<kind>/<int:item_id>/occurrence", methods=["PUT"])
def api_schedule_occurrence(kind, item_id):
    return _complete_schedule_occurrence(session["username"], kind, item_id)


@bp.route("/api/schedule/recurring/<int:item_id>/exception", methods=["POST"])
def api_schedule_exception(item_id):
    return _schedule_exception_response(session["username"], item_id)


@bp.route("/api/agenda")
def api_workspace_agenda():
    return _workspace_agenda_response(session["username"])


@bp.route("/api/actions")
def api_workspace_actions():
    return _workspace_actions_response(session["username"])


@bp.route("/api/actions/<path:ref>", methods=["GET", "PUT"])
def api_workspace_action(ref):
    return _workspace_action_response(session["username"], ref)


@bp.route("/api/projects/<int:project_id>/restore", methods=["POST"])
def api_project_restore(project_id):
    return _manage_project_record(session["username"], project_id, "restore")


@bp.route("/api/projects/<int:project_id>/tasks/<int:task_id>/<operation>", methods=["POST"])
def api_project_task_manage(project_id, task_id, operation):
    if operation not in {"restore", "to-materials"}:
        abort(404)
    return _manage_project_record(session["username"], project_id, operation, task_id)


@bp.route("/api/projects/trash")
def api_project_trash():
    return _project_trash(session["username"])


@bp.route("/api/actions/focus")
def api_project_focus():
    return _project_focus(session["username"])

