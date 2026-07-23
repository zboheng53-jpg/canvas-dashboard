"""Per-user course cache and simple schedule-item storage."""
from datetime import date

from storage import locked_json_update, read_json_file, write_json_file
import user_paths


def _courses_file(username): return user_paths.user_dir(username) / "course_schedule.json"
def _items_file(username): return user_paths.user_dir(username) / "schedule_items.json"


def load_courses(username):
    return read_json_file(_courses_file(username), {"term": "", "semester_start": "", "updated_at": None, "courses": []})


def save_courses(username, term, semester_start, courses, updated_at):
    if not courses:
        return False
    write_json_file(_courses_file(username), {"term": term, "semester_start": semester_start, "updated_at": updated_at, "courses": courses})
    return True


def load_items(username):
    return read_json_file(_items_file(username), {"recurring": [], "one_off": []})


def _next_id(items):
    return max((int(item.get("id", 0)) for item in items if str(item.get("id", "")).isdigit()), default=0) + 1


def create_item(username, kind, item):
    key = "recurring" if kind == "recurring" else "one_off"
    created = {}
    def update(data):
        data.setdefault("recurring", []); data.setdefault("one_off", [])
        entry = dict(item); entry["id"] = _next_id(data[key]); data[key].append(entry); created.update(entry)
        return data
    locked_json_update(_items_file(username), {"recurring": [], "one_off": []}, update)
    return created


def update_item(username, kind, item_id, changes):
    key = "recurring" if kind == "recurring" else "one_off"; updated = {}
    def update(data):
        for item in data.get(key, []):
            if item.get("id") == item_id:
                item.update(changes); updated.update(item); break
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


def today_entries(username, today, semester_start):
    cache, items = load_courses(username), load_items(username)
    timed, deadlines = [], []
    week = ((today - date.fromisoformat(semester_start)).days // 7) + 1 if semester_start else 0
    for course in cache.get("courses", []):
        for session in course.get("sessions", []):
            in_dates = session.get("date_start") and session.get("date_end") and session["date_start"] <= today.isoformat() <= session["date_end"]
            valid_week = session.get("weekday") == today.weekday() and (not session.get("weeks") or week in session["weeks"])
            parity = session.get("parity")
            if parity == "odd" and week % 2 == 0: valid_week = False
            if parity == "even" and week % 2 != 0: valid_week = False
            if in_dates or valid_week:
                timed.append({"kind": "course", "title": course.get("name", "课程"), "location": session.get("location") or course.get("location", ""), "start_time": session["start_time"], "end_time": session["end_time"]})
    for item in items.get("recurring", []):
        today_iso = today.isoformat()
        in_range = (not item.get("start_date") or item["start_date"] <= today_iso) and (not item.get("end_date") or today_iso <= item["end_date"])
        if item.get("enabled", True) and in_range and item.get("weekday") == today.weekday() and today_iso not in item.get("skipped_dates", []):
            timed.append({"kind": "recurring", "title": item["title"], "location": item.get("location", ""), "start_time": item["start_time"], "end_time": item["end_time"]})
    for item in items.get("one_off", []):
        if item.get("date") == today.isoformat():
            timed.append({"kind": "one_off", "title": item["title"], "location": item.get("location", ""), "start_time": item["start_time"], "end_time": item["end_time"]})
    timed.sort(key=lambda item: (item["start_time"], item["end_time"], item["title"]))
    return {"timed": timed, "deadlines": deadlines, "term": cache.get("term", ""), "updated_at": cache.get("updated_at")}
