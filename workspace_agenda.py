"""One date-range projection for the homepage, week planner and Agent API."""
from datetime import date, timedelta

import schedule_store


def build(username, start, end, semester_start, actions):
    courses = schedule_store.load_courses(username)
    semester_start = courses.get("semester_start") or semester_start
    items = schedule_store.load_items(username)
    by_ref = {action["ref"]: action for action in actions}
    days = []
    scheduled_refs = set()
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        day_iso = day.isoformat()
        result = schedule_store.today_entries(username, day, semester_start, courses, items)
        timed = result["timed"]
        for event in timed:
            event["date"] = day_iso
            ref = event.get("action_ref")
            if not ref:
                continue
            action = by_ref.get(ref)
            event["link_missing"] = action is None
            if action is not None:
                event.update(title=action["title"], details=action.get("details", ""),
                             commitment=action["commitment"], done=action["done"],
                             project_name=action.get("project_name"), action=action)
                scheduled_refs.add(ref)
        day_refs = {event.get("action_ref") for event in timed}
        deadlines, planned = [], []
        for action in actions:
            if action["done"] or not action.get("active", True):
                continue
            if action.get("due_date") == day_iso:
                deadlines.append({**action, "action_ref": action["ref"], "kind": "deadline", "date": day_iso})
            if action.get("planned_on") == day_iso and action["ref"] not in day_refs:
                planned.append({**action, "action_ref": action["ref"], "kind": "planned", "date": day_iso})
        timed.sort(key=lambda event: (event["start_time"], event["title"]))
        days.append({"date": day_iso, "timed": timed, "deadlines": deadlines, "planned": planned})
    # No-date responsibilities and growth actions remain findable without inventing times.
    unscheduled = [a for a in actions if not a["done"] and a.get("active", True)
                   and a["ref"] not in scheduled_refs]
    unscheduled.sort(key=lambda a: (a["commitment"] == "growth", a.get("due_date") or a.get("planned_on") or "9999", a["title"]))
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days,
            "unscheduled": unscheduled, "term": courses.get("term", ""),
            "updated_at": courses.get("updated_at")}
