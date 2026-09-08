"""Per-user course cache and simple schedule-item storage."""
from datetime import date, datetime, timezone

from storage import locked_json_update, read_json_file, write_json_file
import user_paths
from action_contract import check_version, fingerprint, replay


def _courses_file(username): return user_paths.user_dir(username) / "course_schedule.json"
def _items_file(username): return user_paths.user_dir(username) / "schedule_items.json"


def load_courses(username):
    return read_json_file(_courses_file(username), {"term": "", "semester_start": "", "updated_at": None, "courses": []})


def save_courses(username, term, semester_start, courses, updated_at):
    if not courses:
        return False
    write_json_file(_courses_file(username), {"term": term, "semester_start": semester_start, "updated_at": updated_at, "courses": courses})
    return True


def clear_courses(username):
    default = {"term": "", "semester_start": "", "updated_at": None, "courses": []}
    locked_json_update(_courses_file(username), default, lambda _data: {"term": "", "semester_start": "", "updated_at": None, "courses": []})
    return True


def delete_course(username, course_identifier):
    default = {"term": "", "semester_start": "", "updated_at": None, "courses": []}
    found = {"value": False}
    target = str(course_identifier)
    def update(data):
        courses = data.get("courses", [])
        new_courses = []
        for idx, course in enumerate(courses):
            cid = str(course.get("id") or course.get("code") or "")
            cname = str(course.get("name") or "")
            if not found["value"] and (cid == target or cname == target or str(idx) == target):
                found["value"] = True
                continue
            new_courses.append(course)
        data["courses"] = new_courses
        if not new_courses:
            data["term"] = ""
            data["semester_start"] = ""
            data["updated_at"] = None
        return data
    locked_json_update(_courses_file(username), default, update)
    return found["value"]


def load_items(username):
    return read_json_file(_items_file(username), {"recurring": [], "one_off": []})


def _next_id(items):
    return max((int(item.get("id", 0)) for item in items if str(item.get("id", "")).isdigit()), default=0) + 1


def create_item(username, kind, item):
    key = "recurring" if kind == "recurring" else "one_off"
    created = {}
    def update(data):
        data.setdefault("recurring", []); data.setdefault("one_off", [])
        existing = replay(data[key], item)
        if existing:
            created.update(existing)
            return data
        entry = dict(item)
        entry["id"] = max(data.get(f"next_{key}_id", 1), _next_id(data[key]))
        data[f"next_{key}_id"] = entry["id"] + 1
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        entry["request_fingerprint"] = fingerprint(item)
        data[key].append(entry)
        created.update(entry)
        return data
    locked_json_update(_items_file(username), {"recurring": [], "one_off": []}, update)
    return created


def update_item(username, kind, item_id, changes):
    key = "recurring" if kind == "recurring" else "one_off"; updated = {}
    def update(data):
        for item in data.get(key, []):
            if item.get("id") == item_id:
                check_version(item, changes)
                item.update({k: v for k, v in changes.items() if k not in ("expected_updated_at", "request_id")})
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                updated.update(item)
                break
        return data
    locked_json_update(_items_file(username), {"recurring": [], "one_off": []}, update)
    return updated or None


def delete_item(username, kind, item_id):
    key = "recurring" if kind == "recurring" else "one_off"; found = {"value": False}
    def update(data):
        original = data.get(key, []); data[key] = [item for item in original if item.get("id") != item_id]
        found["value"] = len(original) != len(data[key]); return data
    locked_json_update(_items_file(username), {"recurring": [], "one_off": []}, update)
    return found["value"]


def complete_occurrence(username, kind, item_id, day, done):
    updated = {}
    def update(data):
        for item in data.get(kind, []):
            if item.get("id") != item_id:
                continue
            if kind == "recurring":
                if (not item.get("enabled", True) or item.get("weekday") != date.fromisoformat(day).weekday()
                        or day in item.get("skipped_dates", [])
                        or (item.get("start_date") and day < item["start_date"])
                        or (item.get("end_date") and day > item["end_date"])):
                    return data
                dates = set(item.get("completed_dates", []))
                dates.add(day) if done else dates.discard(day)
                item["completed_dates"] = sorted(dates)
            elif item.get("date") == day:
                item["occurrence_done"] = done
            else:
                return data
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated.update(item)
            break
        return data
    locked_json_update(_items_file(username), {"recurring": [], "one_off": []}, update)
    return updated or None


def replace_occurrence(username, item_id, day, payload, expected_updated_at=None):
    """Skip the original and create its exception in a single file transaction."""
    result = {}
    def update(data):
        if payload:
            existing = replay(data.get("one_off", []), payload)
            if existing:
                result.update(existing)
                return data
        item = next((i for i in data.get("recurring", []) if i.get("id") == item_id), None)
        if not item:
            return data
        check_version(item, {"expected_updated_at": expected_updated_at})
        if (item.get("weekday") != date.fromisoformat(day).weekday()
                or day in item.get("skipped_dates", [])
                or (item.get("start_date") and day < item["start_date"])
                or (item.get("end_date") and day > item["end_date"])):
            return data
        item["skipped_dates"] = sorted(set(item.get("skipped_dates", [])) | {day})
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        if payload:
            one_off = data.setdefault("one_off", [])
            new_id = max(data.get("next_one_off_id", 1), _next_id(one_off))
            entry = {**payload, "id": new_id, "updated_at": item["updated_at"], "request_fingerprint": fingerprint(payload),
                     "occurrence_done": day in item.get("completed_dates", [])}
            one_off.append(entry)
            data["next_one_off_id"] = new_id + 1
            result.update(entry)
        else:
            result.update(item)
        return data
    locked_json_update(_items_file(username), {"recurring": [], "one_off": []}, update)
    return result or None


def today_entries(username, today, semester_start, cache=None, items=None):
    cache = load_courses(username) if cache is None else cache
    items = load_items(username) if items is None else items
    timed, deadlines = [], []
    week = ((today - date.fromisoformat(semester_start)).days // 7) + 1 if semester_start else 0
    for course_index, course in enumerate(cache.get("courses", [])):
        for session_index, session in enumerate(course.get("sessions", [])):
            in_dates = session.get("date_start") and session.get("date_end") and session["date_start"] <= today.isoformat() <= session["date_end"]
            valid_week = session.get("weekday") == today.weekday() and (week > 0 if semester_start else True) and (not session.get("weeks") or week in session["weeks"])
            parity = session.get("parity")
            if parity == "odd" and (week <= 0 or week % 2 == 0): valid_week = False
            if parity == "even" and (week <= 0 or week % 2 != 0): valid_week = False
            if in_dates if session.get("date_start") and session.get("date_end") else valid_week:
                timed.append({"kind": "course", "uid": f"course-{course_index}-{session_index}", "course_index": course_index, "session": session, "course": course, "title": course.get("name", "课程"), "location": session.get("location") or course.get("location", ""), "start_time": session["start_time"], "end_time": session["end_time"]})
    for item in items.get("recurring", []):
        today_iso = today.isoformat()
        in_range = (not item.get("start_date") or item["start_date"] <= today_iso) and (not item.get("end_date") or today_iso <= item["end_date"])
        if item.get("enabled", True) and in_range and item.get("weekday") == today.weekday() and today_iso not in item.get("skipped_dates", []):
            timed.append({**item, "kind": "recurring", "uid": f"recurring-{item['id']}", "occurrence_done": today_iso in item.get("completed_dates", [])})
    for item in items.get("one_off", []):
        if item.get("date") == today.isoformat():
            timed.append({**item, "kind": "one_off", "uid": f"one_off-{item['id']}", "occurrence_done": bool(item.get("occurrence_done"))})
    timed.sort(key=lambda item: (item["start_time"], item["end_time"], item["title"]))
    return {"timed": timed, "deadlines": deadlines, "term": cache.get("term", ""), "updated_at": cache.get("updated_at")}
