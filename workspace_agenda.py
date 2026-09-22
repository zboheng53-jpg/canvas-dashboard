"""One date-range projection for the homepage, week planner and Agent API."""
from datetime import date, timedelta

import recurring_todo_store
import schedule_store


def build(username, start, end, semester_start, actions):
    courses = schedule_store.load_courses(username)
    semester_start = courses.get("semester_start") or semester_start
    items = schedule_store.load_items(username)
    by_ref = {action["ref"]: action for action in actions}
    days = []
    scheduled_refs = set()

    def _resolve_action(ref):
        if not ref:
            return None
        act = by_ref.get(ref)
        if act is None and ref.startswith("recurring:"):
            act = recurring_todo_store.get_occurrence_by_ref(username, ref)
        return act

    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        day_iso = day.isoformat()
        result = schedule_store.today_entries(username, day, semester_start, courses, items)
        timed = []
        for event in result["timed"]:
            ref = event.get("action_ref")
            if ref:
                action = _resolve_action(ref)
                if not action or not action.get("active", True):
                    continue
            timed.append(event)

        for event in timed:
            event["date"] = day_iso
            ref = event.get("action_ref")
            if not ref:
                continue
            action = _resolve_action(ref)
            event["link_missing"] = action is None
            if action is not None:
                schedule_details = event.get("details", "")
                event.update(title=action["title"],
                             details=schedule_details or action.get("details", ""),
                             schedule_details=schedule_details,
                             action_details=action.get("details", ""),
                             commitment=action["commitment"], done=action["done"],
                             project_name=action.get("project_name"), action=action)
                scheduled_refs.add(ref)
        day_refs = {event.get("action_ref") for event in timed}
        deadlines, planned = [], []
        for action in actions:
            if not action.get("active", True):
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


def focus(actions, agenda, day, schedules):
    """Project focus, derived from the same actions and occurrences as the agenda."""
    today, previous, candidates, overdue = [], [], [], []
    target = day.isoformat()
    events = agenda["days"][0]["timed"]
    future_refs = {item.get("action_ref") for item in schedules.get("one_off", [])
                   if (item.get("date") or "") > target and not item.get("occurrence_done")}
    future_refs.update(item.get("action_ref") for item in schedules.get("recurring", [])
                       if item.get("enabled", True) and (item.get("start_date") or "") > target)
    future_refs.update(e.get("action_ref") for d in agenda["days"][1:] for e in d["timed"] if not e.get("occurrence_done"))
    past_refs = {item.get("action_ref") for item in schedules.get("one_off", [])
                 if (item.get("date") or "") < target and not item.get("occurrence_done")}
    for action in actions:
        if action["source"] != "project" or action["done"] or not action.get("active", True):
            continue
        occurrences = [e for e in events if e.get("action_ref") == action["ref"]]
        pending_occurrences = [e for e in occurrences if not e.get("occurrence_done")]
        item = {**action, "occurrences": occurrences}
        due, planned = action.get("due_date"), action.get("planned_on")
        if due and due < target:
            overdue.append(item)
        if pending_occurrences or due == target or (planned == target and not occurrences):
            today.append(item)
        elif ((planned and planned < target) or (action["ref"] in past_refs)) and not occurrences and action["ref"] not in future_refs:
            previous.append(item)
        elif action.get("is_next_action") and not occurrences and not (planned and planned > target) and action["ref"] not in future_refs:
            candidates.append(item)
    key = lambda a: (a.get("due_date") or "9999", a.get("project_id", 0), a["ref"])
    return {"date": target, "today": sorted(today, key=key), "previous": sorted(previous, key=key),
            "candidates": sorted(candidates, key=key), "overdue": sorted(overdue, key=key)}
