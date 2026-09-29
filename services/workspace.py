"""Shared workspace operations and projections used by browser and Agent routes."""
import platform_sync
import project_store
import re
import recurring_todo_store
import schedule_store
import workspace_agenda
import zhihuishu_store
from action_contract import ActionValidationError, action_fields, check_version, fingerprint, replay, short_title
from canvas_auth import cached_items as canvas_cached_items, has_feed_url, load_state, resolve_item_id as resolve_canvas_item_id, update_state
from datetime import date, datetime, timedelta
from flask import abort, jsonify, request, session
from haoke_client import (
    has_credentials as has_haoke_credentials,
    load_state as load_haoke_state,
    update_state as update_haoke_state,
)
from ketangpai_client import (
    has_token as has_ktp_token,
    load_state as load_ktp_state,
    update_state as update_ktp_state,
)
from services.academic import get_term_info
from storage import locked_json_update, read_json_file, write_json_file
from tongji_oj_client import (
    has_credentials as has_tjoj_credentials,
    load_state as load_tjoj_state,
    update_state as update_tjoj_state,
)
from user_paths import user_dir
from web_common import CST, api_error, invalid_request_response, read_json_request
from zhixuemeng_client import (
    has_token as has_zxm_token,
    load_state as load_zxm_state,
    update_state as update_zxm_state,
)


def _todos_file(username):
    return user_dir(username) / "custom_todos.json"


def _todo_timestamp():
    return datetime.now(CST).isoformat()


def _normalize_todos(todos):
    for todo in todos:
        if "labels" not in todo:
            todo["labels"] = []
        if "subtasks" not in todo:
            todo["subtasks"] = []
        if "updated_at" not in todo:
            # Legacy completed records have no completion timestamp. Preserve
            # their historic expiry behaviour rather than treating migration
            # time as a fresh completion.
            todo["updated_at"] = todo.get("created_at") or (todo.get("due_date") if todo.get("done") and todo.get("due_date") else _todo_timestamp())
    return todos


def _load_todos(username):
    return _normalize_todos(read_json_file(_todos_file(username), []))


def _save_todos(username, todos):
    write_json_file(_todos_file(username), todos)


def _remove_expired_completed_todos(username, today):
    def remove_expired(todos):
        remaining = []
        for todo in _normalize_todos(todos):
            if todo.get("done") and todo.get("due_date"):
                try:
                    due = datetime.fromisoformat(todo["due_date"]).date()
                except (ValueError, TypeError):
                    due = None
                if due and due < today:
                    continue
            remaining.append(todo)
        return remaining

    return locked_json_update(_todos_file(username), [], remove_expired)


def _parse_calendar_due(value):
    try:
        due_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=CST)
    return due_at.astimezone(CST)


CALENDAR_CATEGORIES = {
    "all": {
        "id": "all",
        "name": "Canvas Dashboard · 综合",
        "color": "#4F46E5",
        "description": "全部课程、作业待办、项目计划与日常排程",
    },
    "courses": {
        "id": "courses",
        "name": "Canvas Dashboard · 课表",
        "color": "#2563EB",
        "description": "仅包含学期课表节次与教室地点",
    },
    "assignments": {
        "id": "assignments",
        "name": "Canvas Dashboard · 作业",
        "color": "#DC2626",
        "description": "Canvas、好课、智学盟、智慧树作业与个人待办",
    },
    "projects": {
        "id": "projects",
        "name": "Canvas Dashboard · 计划",
        "color": "#EA580C",
        "description": "长期项目任务与行动推进计划",
    },
    "schedule": {
        "id": "schedule",
        "name": "Canvas Dashboard · 日程",
        "color": "#059669",
        "description": "单次与周期日常排程事项",
    },
}


CATEGORY_ALIASES = {
    "all": "all",
    "course": "courses",
    "courses": "courses",
    "assignment": "assignments",
    "assignments": "assignments",
    "todo": "assignments",
    "todos": "assignments",
    "project": "projects",
    "projects": "projects",
    "plan": "projects",
    "plans": "projects",
    "schedule": "schedule",
    "schedules": "schedule",
}


def _calendar_items(username, category=None):
    now = datetime.now(CST)
    items = []
    cat_key = CATEGORY_ALIASES.get((category or "all").strip().lower(), "all")

    if cat_key in ("all", "assignments"):
        for todo in _load_todos(username):
            if todo.get("done"):
                continue
            if todo.get("due_date"):
                items.append({
                    "source": "Custom",
                    "id": todo.get("id"),
                    "title": todo.get("text"),
                    "due_date": todo.get("due_date"),
                })
            for index, subtask in enumerate(todo.get("subtasks") or [], start=1):
                if not isinstance(subtask, dict) or subtask.get("done") or not subtask.get("due_date"):
                    continue
                subtask_id = subtask.get("id")
                if subtask_id is None:
                    subtask_id = index
                items.append({
                    "source": "Custom",
                    "id": f"{todo.get('id')}-subtask-{subtask_id}",
                    "title": subtask.get("text"),
                    "due_date": subtask.get("due_date"),
                    "course": todo.get("text"),
                })

        today_date = now.date()
        for occ in recurring_todo_store.get_range_occurrences(username, today_date - timedelta(days=30), today_date + timedelta(days=90)):
            if occ["status"] == "pending":
                items.append({
                    "source": "Custom",
                    "id": occ["id"],
                    "uid": f"recurring-{occ['series_id']}-{occ['original_due_date']}",
                    "title": f"↻ {occ['title']}",
                    "due_date": occ["due_date"],
                    "course": "重复待办",
                })

        def is_eligible(platform, legacy_default):
            if platform_sync.is_calendar_eligible(username, platform, legacy_default=legacy_default):
                return True
            status = platform_sync.get(username, platform)
            if status.get("connection_state") == "disconnected":
                return False
            if platform == "canvas" and has_feed_url(username):
                return True
            if platform == "haoke" and has_haoke_credentials(username):
                return True
            if platform == "zhixuemeng" and has_zxm_token(username):
                return True
            if platform == "zhihuishu" and zhihuishu_store.has_cookies(username):
                return True
            if platform == "ketangpai" and has_ktp_token(username):
                return True
            if platform == "tongjioj" and has_tjoj_credentials(username):
                return True
            return status.get("connection_state") == "connected"

        def add_cached(source, platform, cached_items, state, legacy_connected):
            if not is_eligible(platform, legacy_connected):
                return
            hidden = set(state.get("hidden", []))
            deleted = set(state.get("deleted", []))
            completed = set(state.get("completed", []))
            overrides = state.get("overrides", {}) if isinstance(state.get("overrides", {}), dict) else {}
            for item in cached_items:
                item_id = item.get("id")
                override = overrides.get(str(item_id), {})
                due_ts = override.get("due_ts", item.get("due_ts"))
                due_at = _parse_calendar_due(due_ts)
                due_date = item.get("due_date")
                if (
                    item_id in hidden
                    or str(item_id) in hidden
                    or item_id in deleted
                    or str(item_id) in deleted
                    or item_id in completed
                    or str(item_id) in completed
                    or item.get("done")
                ):
                    continue
                if due_at is not None:
                    if due_at < now - timedelta(days=30):
                        continue
                elif due_date:
                    try:
                        d = date.fromisoformat(str(due_date))
                        if d < (now - timedelta(days=30)).date():
                            continue
                    except ValueError:
                        continue
                else:
                    continue
                items.append({
                    "source": source,
                    "id": item_id,
                    "title": override.get("title", item.get("title")),
                    "due_ts": due_ts,
                    "due_date": due_date,
                    "course": item.get("course"),
                    "url": item.get("url"),
                })

        add_cached("Canvas", "canvas", canvas_cached_items(username), load_state(username), True)
        add_cached("Haoke", "haoke", read_json_file(user_dir(username) / "haoke_cache.json", []), load_haoke_state(username), True)
        zxm_cache = read_json_file(user_dir(username) / "zhixuemeng_cache.json", {})
        add_cached("Zhixuemeng", "zhixuemeng", zxm_cache.get("items", []) if isinstance(zxm_cache, dict) else [], load_zxm_state(username), True)
        zhs_cache = zhihuishu_store.load_cache(username)
        add_cached("Zhihuishu", "zhihuishu", zhs_cache["items"], zhihuishu_store.load_state(username), True)
        ktp_cache = read_json_file(user_dir(username) / "ketangpai_cache.json", {})
        add_cached("Ketangpai", "ketangpai", ktp_cache.get("items", []) if isinstance(ktp_cache, dict) else [], load_ktp_state(username), True)
        tjoj_cache = read_json_file(user_dir(username) / "tongjioj_cache.json", {})
        add_cached("TongjiOJ", "tongjioj", tjoj_cache.get("items", []) if isinstance(tjoj_cache, dict) else [], load_tjoj_state(username), True)

    if cat_key in ("all", "projects"):
        for item in project_store.calendar_items(username):
            items.append({
                "source": "Project",
                "id": item["id"],
                "uid": item["uid"],
                "title": item["calendar_title"],
                "due_date": item["due_date"],
                "course": item["project_name"],
            })

    if cat_key in ("all", "courses"):
        courses_data = schedule_store.load_courses(username)
        sem_start = courses_data.get("semester_start")
        if not sem_start:
            try:
                _, _, sem_start = get_term_info()
            except Exception:
                sem_start = None

        if sem_start and courses_data.get("courses"):
            try:
                sem_start_date = date.fromisoformat(sem_start)
            except ValueError:
                sem_start_date = None

            if sem_start_date:
                for c_idx, course in enumerate(courses_data["courses"]):
                    c_name = course.get("name") or "课程"
                    c_code = course.get("code") or course.get("id") or f"c{c_idx}"
                    c_teacher = course.get("teacher") or ""
                    for s_idx, session in enumerate(course.get("sessions") or []):
                        weekday = session.get("weekday")
                        start_time = session.get("start_time")
                        end_time = session.get("end_time")
                        if weekday is None or not start_time or not end_time:
                            continue
                        s_loc = session.get("location") or course.get("location") or ""
                        weeks = session.get("weeks")
                        parity = session.get("parity")
                        date_start = session.get("date_start")
                        date_end = session.get("date_end")

                        if date_start and date_end:
                            try:
                                ds = date.fromisoformat(date_start)
                                de = date.fromisoformat(date_end)
                                curr = ds
                                while curr <= de:
                                    if curr.weekday() == weekday:
                                        day_iso = curr.isoformat()
                                        uid = f"course-{c_code}-{s_idx}-{day_iso}@canvas-dashboard"
                                        desc_lines = [f"课程: {c_name}"]
                                        if s_loc:
                                            desc_lines.append(f"地点: {s_loc}")
                                        if c_teacher:
                                            desc_lines.append(f"教师: {c_teacher}")
                                        if c_code:
                                            desc_lines.append(f"代码: {c_code}")
                                        items.append({
                                            "source": "Course",
                                            "uid": uid,
                                            "title": c_name,
                                            "start_dt": f"{day_iso}T{start_time}:00",
                                            "end_dt": f"{day_iso}T{end_time}:00",
                                            "location": s_loc,
                                            "course": c_name,
                                            "description": "\n".join(desc_lines),
                                        })
                                    curr += timedelta(days=1)
                            except ValueError:
                                pass
                            continue

                        target_weeks = weeks if (weeks and isinstance(weeks, list)) else list(range(1, 19))
                        for w in target_weeks:
                            if parity == "odd" and w % 2 == 0:
                                continue
                            if parity == "even" and w % 2 != 0:
                                continue
                            sess_date = sem_start_date + timedelta(weeks=w - 1, days=weekday)
                            day_iso = sess_date.isoformat()
                            uid = f"course-{c_code}-{s_idx}-{day_iso}@canvas-dashboard"
                            desc_lines = [f"课程: {c_name}"]
                            if s_loc:
                                desc_lines.append(f"地点: {s_loc}")
                            if c_teacher:
                                desc_lines.append(f"教师: {c_teacher}")
                            if c_code:
                                desc_lines.append(f"代码: {c_code}")
                            desc_lines.append(f"第 {w} 周")
                            items.append({
                                "source": "Course",
                                "uid": uid,
                                "title": c_name,
                                "start_dt": f"{day_iso}T{start_time}:00",
                                "end_dt": f"{day_iso}T{end_time}:00",
                                "location": s_loc,
                                "course": c_name,
                                "description": "\n".join(desc_lines),
                            })

    if cat_key in ("all", "schedule"):
        sched_items = schedule_store.load_items(username)
        linked_actions = {a["ref"]: a for a in _workspace_actions(username)}
        for kind in ("one_off", "recurring"):
            visible = []
            for item in sched_items.get(kind, []):
                ref = item.get("action_ref")
                action = linked_actions.get(ref)
                if not action and ref and ref.startswith("recurring:"):
                    action = recurring_todo_store.get_occurrence_by_ref(username, ref)
                if ref and (not action or not action.get("active") or action.get("done")):
                    continue
                sched_details = item.get("details") or ""
                act_details = action.get("details", "") if action else ""
                comb_details = sched_details or act_details
                visible.append({**item, **({"title": action["title"], "details": comb_details, "schedule_details": sched_details, "action_details": act_details} if action else {})})
            sched_items[kind] = visible
        for item in sched_items.get("one_off", []):
            if item.get("occurrence_done"):
                continue
            i_date = item.get("date")
            s_time = item.get("start_time")
            e_time = item.get("end_time")
            if not i_date or not s_time or not e_time:
                continue
            uid = f"schedule-oneoff-{item.get('id')}@canvas-dashboard"
            items.append({
                "source": "Schedule",
                "uid": uid,
                "title": item.get("title") or "排程事项",
                "start_dt": f"{i_date}T{s_time}:00",
                "end_dt": f"{i_date}T{e_time}:00",
                "location": item.get("location") or "",
                "description": item.get("details") or "",
            })

        for item in sched_items.get("recurring", []):
            if not item.get("enabled", True):
                continue
            weekday = item.get("weekday")
            s_time = item.get("start_time")
            e_time = item.get("end_time")
            if weekday is None or not s_time or not e_time:
                continue
            start_limit = item.get("start_date") or (now - timedelta(days=14)).date().isoformat()
            end_limit = item.get("end_date") or (now + timedelta(days=120)).date().isoformat()
            skipped = set(item.get("skipped_dates") or [])
            completed = set(item.get("completed_dates") or [])
            try:
                curr_d = date.fromisoformat(start_limit)
                end_d = date.fromisoformat(end_limit)
                while curr_d.weekday() != weekday:
                    curr_d += timedelta(days=1)
                while curr_d <= end_d:
                    day_iso = curr_d.isoformat()
                    if day_iso not in skipped and day_iso not in completed:
                        uid = f"schedule-recurring-{item.get('id')}-{day_iso}@canvas-dashboard"
                        items.append({
                            "source": "Schedule",
                            "uid": uid,
                            "title": item.get("title") or "周期事项",
                            "start_dt": f"{day_iso}T{s_time}:00",
                            "end_dt": f"{day_iso}T{e_time}:00",
                            "location": item.get("location") or "",
                            "description": item.get("details") or "",
                        })
                    curr_d += timedelta(weeks=1)
            except ValueError:
                pass

    return items


def _recurring_todos_list_response(username):
    store = recurring_todo_store.load_store(username)
    series_list = [s for s in store.get("series", []) if not s.get("deleted_at")]
    return jsonify({"ok": True, "series": series_list})


def _recurring_todo_create_response(username):
    payload = read_json_request()
    if not payload:
        return invalid_request_response()
    created = recurring_todo_store.create_series(username, payload)
    return jsonify({"ok": True, "series": created}), 201


def _recurring_todo_detail_response(username, series_id):
    s = recurring_todo_store.get_series(username, series_id)
    if not s:
        return api_error("series_not_found", "未找到指定重复待办系列", 404)
    today = datetime.now(CST).date()
    start_bound = today - timedelta(days=30)
    end_bound = today + timedelta(days=90)
    occurrences = recurring_todo_store.expand_occurrences(s, start_bound, end_bound)
    return jsonify({"ok": True, "series": s, "occurrences": occurrences})


def _recurring_todo_update_response(username, series_id):
    data = read_json_request()
    if not data:
        return invalid_request_response()
    updated = recurring_todo_store.update_series_rule(username, series_id, data, expected_updated_at=data.get("expected_updated_at"))
    return jsonify({"ok": True, "series": updated})


def _recurring_todo_delete_response(username, series_id):
    deleted = recurring_todo_store.delete_series(username, series_id)
    if not deleted:
        return api_error("series_not_found", "未找到指定重复待办系列", 404)
    return jsonify({"ok": True})


def _recurring_todo_stop_response(username, series_id):
    data = read_json_request() or {}
    updated = recurring_todo_store.stop_series(username, series_id, stop_date=data.get("stop_date"))
    return jsonify({"ok": True, "series": updated})


def _recurring_occurrence_complete_response(username, series_id, date_str):
    data = read_json_request()
    if not data or "done" not in data or type(data["done"]) is not bool:
        return invalid_request_response()
    updated = recurring_todo_store.complete_occurrence(username, series_id, date_str, data["done"])
    return jsonify({"ok": True, "result": updated})


def _recurring_occurrence_skip_response(username, series_id, date_str):
    data = read_json_request() or {}
    skip = data.get("skipped", True)
    updated = recurring_todo_store.skip_occurrence(username, series_id, date_str, skip=skip)
    return jsonify({"ok": True, "result": updated})


def _recurring_occurrence_update_response(username, series_id, date_str):
    data = read_json_request()
    if not data:
        return invalid_request_response()
    updated = recurring_todo_store.update_occurrence(username, series_id, date_str, data)
    return jsonify({"ok": True, "result": updated})


def _schedule_item_payload(data, kind, existing=None):
    if data is None:
        return None
    ref = data.get("action_ref") or None
    username = getattr(request, "agent_username", None) or session.get("username")
    linked = _get_workspace_action(username, ref) if ref else None
    if ref and (linked is None or linked.get("done") or not linked.get("active", True)):
        raise ActionValidationError("关联事项不存在、已完成或已归档，请重新查询事项")
    title = linked["title"] if linked else (existing["title"] if existing and data.get("title") == existing.get("title") else short_title(data.get("title")))
    if not all(isinstance(data.get(key, ""), str) for key in ("start_time", "end_time", "location")):
        return None
    start_time = (data.get("start_time") or "").strip()
    end_time = (data.get("end_time") or "").strip()
    if not title or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end_time) or start_time >= end_time:
        return None
    payload = {
        "action_ref": ref,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "location": (data.get("location") or "").strip(),
    }
    if kind == "recurring":
        weekday = data.get("weekday")
        if type(weekday) is not int or not 0 <= weekday <= 6:
            return None
        payload.update({"weekday": weekday, "enabled": bool(data.get("enabled", True))})
        for field in ("start_date", "end_date"):
            value = data.get(field) or ""
            if not isinstance(value, str):
                return None
            if value:
                try:
                    payload[field] = date.fromisoformat(value).isoformat()
                except ValueError:
                    return None
        if payload.get("end_date") and payload.get("start_date") and payload["end_date"] < payload["start_date"]:
            return None
        if "skipped_dates" in data:
            if not isinstance(data["skipped_dates"], list):
                return None
            try:
                payload["skipped_dates"] = sorted({date.fromisoformat(value).isoformat() for value in data["skipped_dates"]})
            except (ValueError, TypeError):
                return None
    else:
        try:
            payload["date"] = date.fromisoformat(data.get("date") or "").isoformat()
        except (ValueError, TypeError):
            return None
    for field, value in action_fields(data).items():
        if field in {"details", "request_id", "expected_updated_at"}:
            payload[field] = value
    return payload


def _schedule_update_payload(username, kind, item_id, data):
    if data is None:
        return None
    existing = next((item for item in schedule_store.load_items(username).get(kind, []) if item["id"] == item_id), None)
    return _schedule_item_payload({**(existing or {}), **data}, kind, existing=existing)


def _schedule_overlap(username, kind, payload, ignore_id=None):
    items = schedule_store.load_items(username)
    weekday = payload.get("weekday") if kind == "recurring" else date.fromisoformat(payload["date"]).weekday()
    candidate_date = date.fromisoformat(payload["date"]) if kind == "one_off" else None
    courses = schedule_store.load_courses(username)
    for course in courses.get("courses", []):
        for meeting in course.get("sessions", []):
            if candidate_date is None:
                same_day = meeting.get("weekday") == weekday
            elif meeting.get("date_start") and meeting.get("date_end"):
                same_day = meeting["date_start"] <= candidate_date.isoformat() <= meeting["date_end"]
            else:
                same_day = meeting.get("weekday") == weekday
            if same_day and payload["start_time"] < meeting.get("end_time", "") and meeting.get("start_time", "") < payload["end_time"]:
                return True
    for item in items.get("recurring", []):
        if kind == "recurring" and item.get("id") == ignore_id:
            continue
        if item.get("enabled", True) and item.get("weekday") == weekday and payload["start_time"] < item.get("end_time", "") and item.get("start_time", "") < payload["end_time"]:
            return True
    for item in items.get("one_off", []):
        if kind == "one_off" and item.get("id") == ignore_id:
            continue
        if kind == "one_off":
            same_day = item.get("date") == payload.get("date")
        else:
            same_day = date.fromisoformat(item.get("date")).weekday() == weekday if item.get("date") else False
        if same_day and payload["start_time"] < item.get("end_time", "") and item.get("start_time", "") < payload["end_time"]:
            return True
    return False


def _project_payload(data, partial=False):
    if data is None:
        return None
    payload = {}
    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 100:
            return None
        payload["name"] = name
    if "objective" in data:
        objective = (data.get("objective") or "").strip()
        if len(objective) > 240:
            return None
        payload["objective"] = objective
    if "due_date" in data:
        raw = (data.get("due_date") or "").strip()
        try:
            payload["due_date"] = date.fromisoformat(raw).isoformat() if raw else None
        except ValueError:
            return None
    if "due_highlighted" in data:
        if not isinstance(data["due_highlighted"], bool):
            return None
        payload["due_highlighted"] = data["due_highlighted"]
    payload.update(action_fields(data))
    return payload


def _project_task_payload(data, partial=False):
    if data is None:
        return None
    payload = {}
    if not partial or "name" in data:
        payload["name"] = short_title(data.get("name"))
    if "group_id" in data:
        group_id = data.get("group_id")
        if group_id is not None and (not isinstance(group_id, int) or isinstance(group_id, bool) or group_id < 1):
            return None
        payload["group_id"] = group_id
    for field in ("done", "highlighted", "is_next_action"):
        if field in data:
            if not isinstance(data[field], bool):
                return None
            payload[field] = data[field]
    if payload.get("done") and payload.get("is_next_action"):
        return None
    payload.update(action_fields(data))
    return payload


def _project_group_name(data):
    if data is None:
        return None
    name = (data.get("name") or "").strip()
    return name if name and len(name) <= 80 else None


def _project_status_response(project_id, operation):
    project, main_project_id = operation(session["username"], project_id)
    if project is None:
        return api_error("project_not_found", "项目不存在", 404)
    return jsonify({
        "ok": True,
        "project": project,
        "main_project_id": main_project_id,
    })


def _custom_action_ref(todo):
    # A creation token prevents old schedule links binding to reused legacy IDs.
    token = fingerprint({"created_at": todo.get("created_at")})[:12]
    return f"custom:{todo['id']}:{token}"


def _next_todo_id(username: str, current: list[dict]) -> int:
    meta_path = user_dir(username) / "custom_todos_meta.json"
    current_max = max(
        (t.get("id", 0) for t in current if isinstance(t.get("id"), int) and not isinstance(t.get("id"), bool)),
        default=0,
    )
    selected = {}
    def allocate(meta):
        stored_next = meta.get("next_id", 0) if isinstance(meta.get("next_id"), int) else 0
        selected["id"] = max(current_max + 1, stored_next)
        return {"next_id": selected["id"] + 1}
    locked_json_update(meta_path, {}, allocate)
    return selected["id"]


def _create_custom_action(username, data):
    if data and "request_id" not in data:
        header_key = request.headers.get("Idempotency-Key") if request else None
        if header_key and header_key.strip():
            data = dict(data, request_id=header_key.strip())
    fields = action_fields(data)
    if fields.get("commitment", "obligation") != "obligation":
        raise ActionValidationError("成长练习请使用项目行动工具；待办用于必须履行的责任")
    payload = {"text": short_title(data.get("text")), **fields}
    payload["labels"] = data.get("labels", []) if isinstance(data.get("labels", []), list) else []
    created = {}

    def add(current):
        current = _normalize_todos(current)
        existing = replay(current, payload)
        if existing:
            created.update(existing)
            return current
        now = _todo_timestamp()
        todo = {"id": _next_todo_id(username, current),
                "done": False, "created_at": now, "updated_at": now,
                "due_date": None, "planned_on": None, "details": "", "commitment": "obligation",
                "highlighted": False, "subtasks": [], **payload,
                "request_fingerprint": fingerprint(payload)}
        current.append(todo)
        created.update(todo)
        return current

    locked_json_update(_todos_file(username), [], add)
    created["ref"] = _custom_action_ref(created)
    return created


def _workspace_actions(username, range_bounds=None):
    actions = []
    for todo in _load_todos(username):
        actions.append({**todo, "ref": _custom_action_ref(todo), "title": todo.get("text", ""),
                        "source": "custom", "commitment": "obligation", "active": True,
                        "editable": True, "details": todo.get("details", "")})
        for index, subtask in enumerate(todo.get("subtasks") or [], 1):
            if isinstance(subtask, dict):
                actions.append({**subtask, "ref": f"{_custom_action_ref(todo)}:subtask:{subtask.get('id', index)}",
                                "parent_ref": _custom_action_ref(todo), "title": subtask.get("text", ""), "course": todo.get("text", ""),
                                "source": "custom_subtask", "commitment": "obligation", "active": not todo.get("done"),
                                "done": bool(todo.get("done") or subtask.get("done")), "editable": False})
    if range_bounds:
        start_d, end_d = range_bounds
        r_items = recurring_todo_store.get_range_occurrences(username, start_d, end_d)
    else:
        r_items = recurring_todo_store.get_homepage_items(username)
    for r_item in r_items:
        actions.append({
            **r_item,
            "ref": r_item["action_ref"],
            "title": r_item["title"],
            "source": "recurring",
            "course": f"重复待办 · {r_item.get('repeat_label', '')}",
            "commitment": "obligation",
            "active": r_item.get("active", True),
            "editable": True,
            "details": r_item.get("details", ""),
        })
    for project in project_store.load_projects(username, include_deleted=True):
        active = project["status"] == "active" and not project.get("deleted_at")
        common = {"project_id": project["id"], "project_name": project["name"], "active": active}
        if project.get("due_date"):
            actions.append({**common, "ref": f"project_due:{project['id']}", "source": "project_due", "deleted_at": project.get("deleted_at"),
                            "title": f"完成项目：{project['name']}", "details": project.get("objective", ""),
                            "due_date": project["due_date"], "commitment": "obligation", "done": not active,
                            "editable": False})
        for task in project["tasks"]:
            actions.append({**task, **common, "ref": f"project:{project['id']}:{task['id']}",
                            "source": "project", "task_id": task["id"], "title": task["name"],
                            "deleted_at": task.get("deleted_at") or project.get("deleted_at"),
                            "active": active and not task.get("deleted_at"),
                            "editable": active and not task.get("deleted_at")})
    for todo in _aggregate_agent_todos(username, status="all", _include_focus=False):
        if todo["source"] in {"custom", "custom_subtask", "project", "recurring"}:
            continue
        due = _parse_calendar_due(todo.get("due_date"))
        actions.append({**todo, "ref": f"{todo['source']}:{todo['id']}", "commitment": "obligation",
                        "due_date": due.date().isoformat() if due else None,
                        "deadline_time": due.strftime("%H:%M") if due else None,
                        "details": todo.get("original_title") or todo["title"], "editable": False, "active": True})
    return actions


def _get_workspace_action(username, ref):
    if ref and ref.startswith("canvas:"):
        canvas_cached_items(username)
        ref = "canvas:" + resolve_canvas_item_id(username, ref[len("canvas:"):])
    if ref and ref.startswith("recurring:"):
        return recurring_todo_store.get_occurrence_by_ref(username, ref)
    return next((action for action in _workspace_actions(username) if action["ref"] == ref and not action.get("deleted_at")), None)


def _workspace_agenda(username, start, end):
    _, _, semester_start = get_term_info()
    return workspace_agenda.build(username, start, end, semester_start, _workspace_actions(username, range_bounds=(start, end)))


def _project_focus_data(username):
    today = datetime.now(CST).date()
    actions = _workspace_actions(username)
    agenda = _workspace_agenda(username, today, today + timedelta(days=13))
    return workspace_agenda.focus(actions, agenda, today, schedule_store.load_items(username))


def _workspace_day(username, day):
    agenda = _workspace_agenda(username, day, day)
    result = agenda["days"][0]
    # Keep the old timed-deadline shape for existing clients; the range API has
    # a separate deadline band, with exact deadline_time where available.
    for item in list(result["deadlines"]):
        if item.get("deadline_time") and item["deadline_time"] != "00:00":
            result["timed"].append({**item, "start_time": item["deadline_time"], "end_time": item["deadline_time"]})
            result["deadlines"].remove(item)
    result["timed"].sort(key=lambda item: (item["start_time"], item["title"]))
    return {**result, "term": agenda["term"], "updated_at": agenda["updated_at"]}


def _complete_schedule_occurrence(username, kind, item_id):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    data = read_json_request() or {}
    day = action_fields({"planned_on": data.get("date")}).get("planned_on")
    if not day or type(data.get("done")) is not bool:
        return invalid_request_response()
    item = schedule_store.complete_occurrence(username, kind.replace("-", "_"), item_id, day, data["done"])
    if item is None:
        return api_error("occurrence_not_found", "这一天没有该时间安排", 404)
    return jsonify({"ok": True, "item": item})


def _schedule_exception_response(username, item_id):
    data = read_json_request() or {}
    day = action_fields({"planned_on": data.get("date")}).get("planned_on")
    if not day:
        return invalid_request_response()
    changes = None
    if not data.get("cancel"):
        target_day = action_fields({"planned_on": data["changes"].get("date") or day}).get("planned_on")
        if not target_day:
            return invalid_request_response()
        changes = _schedule_item_payload({**data["changes"], "date": target_day}, "one_off")
        if changes is None:
            return invalid_request_response()
    item = schedule_store.replace_occurrence(username, item_id, day, changes, data.get("expected_updated_at"))
    if item is None:
        return api_error("occurrence_not_found", "这一天没有该重复安排，请刷新后重试", 404)
    return jsonify({"ok": True, "item": item})


def _workspace_agenda_response(username):
    try:
        start = date.fromisoformat(request.args.get("start") or datetime.now(CST).date().isoformat())
        end = date.fromisoformat(request.args.get("end") or (start + timedelta(days=6)).isoformat())
        if not 0 <= (end - start).days <= 62:
            raise ValueError()
    except (TypeError, ValueError):
        raise ActionValidationError("日期范围请使用 YYYY-MM-DD，最多查询 63 天") from None
    return jsonify({"ok": True, **_workspace_agenda(username, start, end),
                    "sync_status": platform_sync.load(username)["platforms"]})


def _workspace_actions_response(username):
    query = request.args.get("q", "").strip().casefold()
    actions = [a for a in _workspace_actions(username) if not a.get("deleted_at")]
    if request.args.get("status", "pending") != "all":
        actions = [a for a in actions if not a["done"] and a.get("active", True)]
    if query:
        actions = [a for a in actions if query in " ".join(str(a.get(k) or "") for k in ("title", "details", "project_name")).casefold()]
    return jsonify({"ok": True, "actions": actions})


def _workspace_action_response(username, ref):
    action = _get_workspace_action(username, ref)
    if action is None:
        return api_error("action_not_found", "事项不存在或已移除", 404)
    if request.method == "PUT":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        if not action.get("active", True):
            raise ActionValidationError("请先重新开启所属项目")
        if action["source"] == "project":
            changes = _project_task_payload({**data, **({"name": data["title"]} if "title" in data else {})}, partial=True)
            if not changes:
                return invalid_request_response()
            project_store.update_task(username, action["project_id"], action["task_id"], changes)
        elif action["source"] == "custom":
            changes = action_fields(data)
            if "title" in data:
                changes["text"] = short_title(data["title"])
            if "done" in data:
                if type(data["done"]) is not bool:
                    return invalid_request_response()
                changes["done"] = data["done"]
            if changes.get("commitment", "obligation") != "obligation":
                raise ActionValidationError("成长行动请在长期项目中创建")
            def update(current):
                for todo in _normalize_todos(current):
                    if _custom_action_ref(todo) == ref:
                        check_version(todo, changes)
                        todo.update({k: v for k, v in changes.items() if k not in ("expected_updated_at", "request_id")})
                        todo["updated_at"] = _todo_timestamp()
                        if "done" in changes:
                            todo["completed_at"] = _todo_timestamp() if changes["done"] else None
                return current
            locked_json_update(_todos_file(username), [], update)
        elif action["source"] in {"canvas", "haoke", "zhixuemeng", "zhihuishu", "ketangpai", "tongjioj"} and "done" in data:
            if type(data["done"]) is not bool:
                return invalid_request_response()
            target_state = "complete" if data["done"] else "uncomplete"
            if action["source"] == "canvas":
                update_state(username, target_state, action["id"])
            elif action["source"] == "haoke":
                update_haoke_state(username, target_state, action["id"])
            elif action["source"] == "zhixuemeng":
                update_zxm_state(username, target_state, action["id"])
            elif action["source"] == "zhihuishu":
                zhihuishu_store.update_state(username, target_state, action["id"])
            elif action["source"] == "ketangpai":
                update_ktp_state(username, target_state, action["id"])
            elif action["source"] == "tongjioj":
                update_tjoj_state(username, target_state, action["id"])
        elif action["source"] == "recurring":
            changes = action_fields(data)
            series_id = action["series_id"]
            orig_due_date = action["original_due_date"]
            if "title" in data:
                changes["title"] = short_title(data["title"])
            if "done" in data:
                if type(data["done"]) is not bool:
                    return invalid_request_response()
                recurring_todo_store.complete_occurrence(username, series_id, orig_due_date, data["done"])
            if "skipped" in data:
                if type(data["skipped"]) is not bool:
                    return invalid_request_response()
                recurring_todo_store.skip_occurrence(username, series_id, orig_due_date, data["skipped"])
            occ_changes = {k: v for k, v in changes.items() if k in ("title", "details", "due_date")}
            if occ_changes:
                recurring_todo_store.update_occurrence(username, series_id, orig_due_date, occ_changes)
        else:
            raise ActionValidationError("此事项请从原始入口编辑")
        action = _get_workspace_action(username, ref)
    schedules = schedule_store.load_items(username)
    linked = [{**item, "kind": kind} for kind in ("recurring", "one_off")
              for item in schedules.get(kind, []) if item.get("action_ref") == ref]
    return jsonify({"ok": True, "action": action, "schedules": linked})


def _aggregate_agent_todos(username: str, source: str = "all", status: str = "pending", _include_focus: bool = True) -> list[dict]:
    all_todos = []

    # 1. Custom todos
    for t in _load_todos(username):
        parent_done = bool(t.get("done"))
        all_todos.append({
            "id": str(t.get("id")),
            "title": t.get("text", ""),
            "ref": _custom_action_ref(t),
            "details": t.get("details", ""),
            "planned_on": t.get("planned_on"),
            "commitment": "obligation",
            "course": None,
            "due_date": t.get("due_date"),
            "source": "custom",
            "done": parent_done,
            "labels": t.get("labels", []),
            "url": None,
        })
        for index, subtask in enumerate(t.get("subtasks") or [], 1):
            if isinstance(subtask, dict):
                sub_id = subtask.get("id", index)
                all_todos.append({
                    "id": f"{t.get('id')}:{sub_id}",
                    "title": subtask.get("text", ""),
                    "ref": f"{_custom_action_ref(t)}:subtask:{sub_id}",
                    "parent_ref": _custom_action_ref(t),
                    "parent_id": str(t.get("id")),
                    "course": t.get("text", ""),
                    "details": "",
                    "planned_on": subtask.get("planned_on"),
                    "commitment": "obligation",
                    "due_date": subtask.get("due_date"),
                    "source": "custom_subtask",
                    "done": bool(parent_done or subtask.get("done")),
                    "labels": [],
                    "url": None,
                })

    # 1.5 Recurring todos
    if source in ("all", "custom", "recurring"):
        today = datetime.now(CST).date()
        for r in recurring_todo_store.get_homepage_items(username, today=today):
            all_todos.append({
                "id": r["id"],
                "title": r["title"],
                "ref": r["action_ref"],
                "details": r.get("details", ""),
                "planned_on": None,
                "commitment": "obligation",
                "course": "重复待办",
                "due_date": r["due_date"],
                "source": "custom",
                "source_type": "recurring",
                "is_recurring": True,
                "series_id": r["series_id"],
                "original_due_date": r["original_due_date"],
                "done": r["done"],
                "labels": [f"↻ {r['repeat_label']}"],
                "url": None,
            })

    # 2. Platform items
    def add_platform_items(platform_name: str, cache_file: str, state_loader):
        cache_path = user_dir(username) / cache_file
        if not cache_path.exists():
            return
        cached = canvas_cached_items(username) if platform_name == "canvas" else read_json_file(cache_path, [] if platform_name not in ("zhixuemeng", "ketangpai", "tongjioj") else {})
        items = cached.get("items", []) if isinstance(cached, dict) else (cached if isinstance(cached, list) else [])
        state = state_loader(username)
        completed_set = set(state.get("completed", []))
        hidden_set = set(state.get("hidden", []))
        deleted_set = set(state.get("deleted", []))
        overrides = state.get("overrides", {})

        for item in items:
            item_id = item.get("id")
            if (
                item_id in hidden_set
                or str(item_id) in hidden_set
                or item_id in deleted_set
                or str(item_id) in deleted_set
            ):
                continue
            override = overrides.get(str(item_id), {}) if isinstance(overrides, dict) else {}
            title = override.get("title", item.get("title", ""))
            due_ts = override.get("due_ts", item.get("due_ts"))
            is_done = (
                item_id in completed_set
                or str(item_id) in completed_set
                or bool(item.get("done"))
            )
            all_todos.append({
                "id": str(item_id),
                "title": title,
                "original_title": item.get("title", ""),
                "course": item.get("course"),
                "due_date": due_ts,
                "source": platform_name,
                "done": is_done,
                "labels": [],
                "url": item.get("url"),
            })

    add_platform_items("canvas", "canvas_cache.json", load_state)
    add_platform_items("haoke", "haoke_cache.json", load_haoke_state)
    add_platform_items("zhixuemeng", "zhixuemeng_cache.json", load_zxm_state)
    add_platform_items("zhihuishu", "zhihuishu_cache.json", zhihuishu_store.load_state)
    add_platform_items("ketangpai", "ketangpai_cache.json", load_ktp_state)
    add_platform_items("tongjioj", "tongjioj_cache.json", load_tjoj_state)

    # 3. Project tasks
    seen_project_refs = set()
    for item in project_store.todo_items(username):
        ref = item.get("action_ref") or f"project_due:{item['project_id']}"
        seen_project_refs.add(ref)
        all_todos.append({
            "id": str(item["id"]),
            "title": item["title"],
            "ref": ref,
            "commitment": item.get("commitment", "obligation"),
            "course": item["project_name"],
            "due_date": item.get("due_date"),
            "source": "project",
            "done": bool(item.get("done")),
            "labels": [],
            "url": None,
        })

    if _include_focus and source in ("all", "project"):
        try:
            f_data = _project_focus_data(username)
            for act in f_data.get("today", []):
                ref = act.get("ref") or act.get("action_ref")
                if ref and ref not in seen_project_refs and not act.get("done"):
                    seen_project_refs.add(ref)
                    all_todos.append({
                        "id": str(act.get("task_id") or act.get("id")),
                        "title": act.get("title") or act.get("name", ""),
                        "ref": ref,
                        "commitment": act.get("commitment", "growth"),
                        "course": act.get("project_name", ""),
                        "due_date": act.get("due_date") or act.get("planned_on"),
                        "planned_on": act.get("planned_on"),
                        "source": "project",
                        "done": False,
                        "labels": [],
                        "url": None,
                    })
        except Exception:
            pass

    # Filtering
    filtered = []
    source_lower = source.lower() if source else "all"
    for item in all_todos:
        item_source = item["source"].lower()
        if source_lower != "all":
            if source_lower == "custom":
                if item_source not in ("custom", "custom_subtask"):
                    continue
            elif item_source != source_lower:
                continue
        if status == "pending" and item["done"]:
            continue
        if status == "completed" and not item["done"]:
            continue
        filtered.append(item)

    filtered.sort(key=lambda t: (
        1 if t["done"] else 0,
        0 if t.get("due_date") else 1,
        t.get("due_date") or "9999-99-99",
    ))
    return filtered


def _platform_item_exists(username: str, platform_name: str, cache_file: str, item_id: str) -> bool:
    cache_path = user_dir(username) / cache_file
    if not cache_path.exists():
        return False
    cached = canvas_cached_items(username) if platform_name == "canvas" else read_json_file(cache_path, [] if platform_name not in ("zhixuemeng", "ketangpai", "tongjioj") else {})
    items = cached.get("items", []) if isinstance(cached, dict) else (cached if isinstance(cached, list) else [])
    str_id = resolve_canvas_item_id(username, item_id) if platform_name == "canvas" else str(item_id)
    return any(str(item.get("id")) == str_id for item in items if isinstance(item, dict))


def _complete_agent_todo(username: str, todo_id: str, source: str = "custom") -> bool:
    source = (source or "custom").lower()
    if source in ("custom", "custom_subtask"):
        parent_id = None
        sub_id = None
        int_id = None
        if ":" in str(todo_id):
            parts = str(todo_id).split(":", 1)
            try:
                parent_id = int(parts[0])
                sub_id = int(parts[1])
            except ValueError:
                pass
        else:
            try:
                int_id = int(todo_id)
            except ValueError:
                int_id = None

        found = {"value": False}
        def update_todos(current):
            for t in _normalize_todos(current):
                if sub_id is not None:
                    if t["id"] == parent_id:
                        for s in t.get("subtasks") or []:
                            if s.get("id") == sub_id or str(s.get("id")) == str(sub_id):
                                s["done"] = True
                                t["updated_at"] = _todo_timestamp()
                                found["value"] = True
                                break
                else:
                    if t["id"] == int_id or str(t["id"]) == str(todo_id):
                        t["done"] = True
                        t["completed_at"] = _todo_timestamp()
                        t["updated_at"] = _todo_timestamp()
                        found["value"] = True
                        break
            return current
        locked_json_update(_todos_file(username), [], update_todos)
        return found["value"]

    elif source == "canvas":
        if not _platform_item_exists(username, "canvas", "canvas_cache.json", todo_id):
            return False
        update_state(username, "complete", todo_id)
        return True
    elif source == "haoke":
        if not _platform_item_exists(username, "haoke", "haoke_cache.json", todo_id):
            return False
        update_haoke_state(username, "complete", todo_id)
        return True
    elif source == "zhixuemeng":
        if not _platform_item_exists(username, "zhixuemeng", "zhixuemeng_cache.json", todo_id):
            return False
        update_zxm_state(username, "complete", todo_id)
        return True
    elif source == "zhihuishu":
        if not _platform_item_exists(username, "zhihuishu", "zhihuishu_cache.json", todo_id):
            return False
        zhihuishu_store.update_state(username, "complete", todo_id)
        return True
    elif source == "ketangpai":
        if not _platform_item_exists(username, "ketangpai", "ketangpai_cache.json", todo_id):
            return False
        update_ktp_state(username, "complete", todo_id)
        return True
    elif source == "tongjioj":
        if not _platform_item_exists(username, "tongjioj", "tongjioj_cache.json", todo_id):
            return False
        update_tjoj_state(username, "complete", todo_id)
        return True
    elif source == "recurring" or str(todo_id).startswith("recurring_"):
        parts = str(todo_id).split("_")
        if len(parts) >= 3:
            try:
                s_id = int(parts[1])
                orig_d = "_".join(parts[2:])
                recurring_todo_store.complete_occurrence(username, s_id, orig_d, True)
                return True
            except Exception:
                return False
        return False
    elif source == "project":
        due_match = re.fullmatch(r"due-(\d+)", str(todo_id))
        if due_match:
            project_id = int(due_match[1])
            return project_store.complete_project(username, project_id) is not None
        match = re.fullmatch(r"task-(\d+)-(\d+)", str(todo_id))
        if not match:
            return False
        return project_store.update_task(username, int(match[1]), int(match[2]), {"done": True}) is not None

    return False


def _manage_project_record(username, project_id, operation, task_id=None):
    data = read_json_request() or {}
    changes = action_fields(data)
    if operation == "to-materials":
        version = data.get("expected_project_updated_at")
        if not isinstance(version, str) or not version.strip():
            raise ActionValidationError("转为资料前请读取项目版本 expected_project_updated_at")
        changes["expected_project_updated_at"] = version
    project = project_store.manage_record(username, project_id, operation, changes, task_id)
    if project is None:
        return api_error("project_record_not_found", "项目或任务不存在", 404)
    return jsonify({"ok": True, "project": project})


def _project_trash(username):
    return jsonify({"ok": True, "projects": [], "tasks": []})


def _project_focus(username):
    return jsonify({"ok": True, **_project_focus_data(username)})

