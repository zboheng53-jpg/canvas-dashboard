"""Recurring todo storage and occurrence expansion.

Each recurring series generates one pending item at a time for the homepage,
strictly selecting the earliest pending (uncompleted, unskipped) occurrence.
Overdue occurrences block subsequent ones until completed or skipped.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import user_paths
from storage import locked_json_update, read_json_file
from action_contract import (
    ActionConflictError,
    ActionValidationError,
    check_version,
    fingerprint,
    replay,
    short_title,
)

CST = ZoneInfo("Asia/Shanghai")


def _store_file(username):
    return user_paths.user_dir(username) / "recurring_todos.json"


def _empty_store():
    return {"version": 1, "next_series_id": 1, "series": []}


def _now_iso():
    return datetime.now(CST).isoformat()


def load_store(username):
    return read_json_file(_store_file(username), _empty_store())


def get_series(username, series_id):
    store = load_store(username)
    for s in store.get("series", []):
        if s.get("id") == int(series_id) and not s.get("deleted_at"):
            return s
    return None


def _validate_series_payload(payload):
    title = short_title(payload.get("title") or payload.get("text"))
    first_due = payload.get("first_due_date") or payload.get("due_date")
    if not first_due:
        raise ActionValidationError("首次截止日期不能为空，格式为 YYYY-MM-DD")
    try:
        first_due_date = date.fromisoformat(first_due)
    except (TypeError, ValueError):
        raise ActionValidationError("首次截止日期格式不正确，请使用 YYYY-MM-DD")

    interval_weeks = payload.get("interval_weeks")
    if interval_weeks is None:
        interval_weeks = 1
    if interval_weeks not in (1, 2):
        raise ActionValidationError("重复间隔必须为 1（每周）或 2（隔周）")

    end_date = payload.get("end_date")
    if end_date:
        try:
            end_d = date.fromisoformat(end_date)
        except (TypeError, ValueError):
            raise ActionValidationError("结束日期格式不正确，请使用 YYYY-MM-DD") from None
        if end_d < first_due_date:
            raise ActionValidationError("结束日期不能早于首次截止日期")
        end_date = end_d.isoformat()
    else:
        end_date = None

    details = (payload.get("details") or "").strip()
    if len(details) > 12000:
        raise ActionValidationError("详情最多 12000 字")

    return {
        "title": title,
        "details": details,
        "first_due_date": first_due_date.isoformat(),
        "interval_weeks": int(interval_weeks),
        "end_date": end_date,
    }


def create_series(username, payload):
    clean = _validate_series_payload(payload)
    created = {}

    def update(store):
        store.setdefault("series", [])
        existing = replay(store["series"], payload)
        if existing:
            created.update(existing)
            return store

        series_id = max(store.get("next_series_id", 1), max((s.get("id", 0) for s in store["series"]), default=0) + 1)
        store["next_series_id"] = series_id + 1

        now = _now_iso()
        entry = {
            "id": series_id,
            "title": clean["title"],
            "details": clean["details"],
            "first_due_date": clean["first_due_date"],
            "interval_weeks": clean["interval_weeks"],
            "end_date": clean["end_date"],
            "stopped_at": None,
            "created_at": now,
            "updated_at": now,
            "request_id": payload.get("request_id"),
            "request_fingerprint": fingerprint(payload),
            "rule_segments": [
                {
                    "effective_from": clean["first_due_date"],
                    "interval_weeks": clean["interval_weeks"],
                    "end_date": clean["end_date"],
                }
            ],
            "occurrences": {},
        }
        store["series"].append(entry)
        created.update(entry)
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    return created


def update_series_rule(username, series_id, changes, expected_updated_at=None):
    series_id = int(series_id)
    updated = {}

    def update(store):
        for s in store.get("series", []):
            if s.get("id") != series_id or s.get("deleted_at"):
                continue
            if expected_updated_at:
                check_version(s, {"expected_updated_at": expected_updated_at})

            if "title" in changes:
                s["title"] = short_title(changes["title"])
            if "details" in changes:
                det = (changes["details"] or "").strip()
                if len(det) > 12000:
                    raise ActionValidationError("详情最多 12000 字")
                s["details"] = det

            if "interval_weeks" in changes or "end_date" in changes:
                new_interval = changes.get("interval_weeks", s.get("interval_weeks", 1))
                if new_interval not in (1, 2):
                    raise ActionValidationError("重复间隔必须为 1 或 2")
                new_end = changes.get("end_date", s.get("end_date"))
                if new_end:
                    new_end = date.fromisoformat(new_end).isoformat()

                effective_from = changes.get("effective_from")
                if effective_from:
                    effective_from = date.fromisoformat(effective_from).isoformat()
                else:
                    # 默认使用最近一次尚未到期的日期
                    today_str = datetime.now(CST).date().isoformat()
                    all_occs = expand_occurrences(s, date.fromisoformat(s["first_due_date"]), datetime.now(CST).date() + timedelta(days=60))
                    future_occs = [o for o in all_occs if o["due_date"] >= today_str and o["status"] == "pending"]
                    effective_from = future_occs[0]["original_due_date"] if future_occs else today_str

                s.setdefault("rule_segments", [])
                s["rule_segments"].append({
                    "effective_from": effective_from,
                    "interval_weeks": int(new_interval),
                    "end_date": new_end,
                })
                s["interval_weeks"] = int(new_interval)
                s["end_date"] = new_end

            s["updated_at"] = _now_iso()
            updated.update(s)
            break
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    if not updated:
        raise ActionValidationError("未找到指定重复待办系列")
    return updated


def stop_series(username, series_id, stop_date=None):
    series_id = int(series_id)
    if not stop_date:
        stop_date = datetime.now(CST).date().isoformat()
    updated = {}

    def update(store):
        for s in store.get("series", []):
            if s.get("id") == series_id and not s.get("deleted_at"):
                s["stopped_at"] = stop_date
                s["updated_at"] = _now_iso()
                updated.update(s)
                break
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    if not updated:
        raise ActionValidationError("未找到指定重复待办系列")
    return updated


def delete_series(username, series_id):
    series_id = int(series_id)
    found = {"value": False}

    def update(store):
        for s in store.get("series", []):
            if s.get("id") == series_id and not s.get("deleted_at"):
                s["deleted_at"] = _now_iso()
                s["updated_at"] = s["deleted_at"]
                found["value"] = True
                break
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    return found["value"]


def complete_occurrence(username, series_id, orig_due_date, done):
    series_id = int(series_id)
    orig_due_date = date.fromisoformat(orig_due_date).isoformat()
    updated = {}

    def update(store):
        for s in store.get("series", []):
            if s.get("id") != series_id or s.get("deleted_at"):
                continue
            occs = s.setdefault("occurrences", {})
            occ = occs.setdefault(orig_due_date, {})
            if done:
                occ["status"] = "completed"
                occ["completed_at"] = _now_iso()
                occ["skipped_at"] = None
            else:
                occ["status"] = "pending"
                occ["completed_at"] = None
                occ["skipped_at"] = None
            occ["updated_at"] = _now_iso()
            s["updated_at"] = occ["updated_at"]
            updated.update({"series": s, "occurrence": occ})
            break
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    if not updated:
        raise ActionValidationError("未找到指定的重复待办或该期次不可操作")
    return updated


def skip_occurrence(username, series_id, orig_due_date, skip=True):
    series_id = int(series_id)
    orig_due_date = date.fromisoformat(orig_due_date).isoformat()
    updated = {}

    def update(store):
        for s in store.get("series", []):
            if s.get("id") != series_id or s.get("deleted_at"):
                continue
            occs = s.setdefault("occurrences", {})
            occ = occs.setdefault(orig_due_date, {})
            if skip:
                occ["status"] = "skipped"
                occ["skipped_at"] = _now_iso()
                occ["completed_at"] = None
            else:
                occ["status"] = "pending"
                occ["skipped_at"] = None
                occ["completed_at"] = None
            occ["updated_at"] = _now_iso()
            s["updated_at"] = occ["updated_at"]
            updated.update({"series": s, "occurrence": occ})
            break
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    if not updated:
        raise ActionValidationError("未找到指定的重复待办或该期次不可操作")
    return updated


def update_occurrence(username, series_id, orig_due_date, changes):
    series_id = int(series_id)
    orig_due_date = date.fromisoformat(orig_due_date).isoformat()
    updated = {}

    def update(store):
        for s in store.get("series", []):
            if s.get("id") != series_id or s.get("deleted_at"):
                continue
            occs = s.setdefault("occurrences", {})
            occ = occs.setdefault(orig_due_date, {})

            if "title" in changes:
                occ["title"] = short_title(changes["title"]) if changes["title"] else None
            if "details" in changes:
                occ["details"] = (changes["details"] or "").strip() if changes["details"] is not None else None
            if "due_date" in changes:
                due_val = changes["due_date"]
                occ["due_date"] = date.fromisoformat(due_val).isoformat() if due_val else None

            occ["updated_at"] = _now_iso()
            s["updated_at"] = occ["updated_at"]
            updated.update({"series": s, "occurrence": occ})
            break
        return store

    locked_json_update(_store_file(username), _empty_store(), update)
    if not updated:
        raise ActionValidationError("未找到指定的重复待办或该期次不可操作")
    return updated


def expand_occurrences(series, start_bound, end_bound, max_count=100):
    """Expand scheduled occurrences between start_bound and end_bound."""
    if series.get("deleted_at"):
        return []

    first_due = date.fromisoformat(series["first_due_date"])
    interval_weeks = series.get("interval_weeks", 1)
    series_end = date.fromisoformat(series["end_date"]) if series.get("end_date") else None
    stopped_at = date.fromisoformat(series["stopped_at"]) if series.get("stopped_at") else None
    rule_segments = series.get("rule_segments") or []

    # 按原定规则生成期次序列
    occurrences = []
    current_due = first_due
    step_days = interval_weeks * 7

    # 处理分段规则辅助
    def get_rule_for_date(d):
        for seg in reversed(rule_segments):
            seg_start = date.fromisoformat(seg["effective_from"])
            if d >= seg_start:
                return seg
        return {"interval_weeks": interval_weeks, "end_date": series.get("end_date")}

    count = 0
    while count < max_count:
        if series_end and current_due > series_end:
            break
        if stopped_at and current_due > stopped_at:
            break

        current_iso = current_due.isoformat()
        occ_meta = (series.get("occurrences") or {}).get(current_iso, {})
        status = occ_meta.get("status", "pending")
        effective_due = occ_meta.get("due_date") or current_iso
        effective_title = occ_meta.get("title") or series["title"]
        effective_details = occ_meta.get("details") if occ_meta.get("details") is not None else series.get("details", "")

        item = {
            "id": f"recurring_{series['id']}_{current_iso}",
            "series_id": series["id"],
            "original_due_date": current_iso,
            "due_date": effective_due,
            "due_str": effective_due,
            "due_ts": f"{effective_due}T23:59:59",
            "title": effective_title,
            "details": effective_details,
            "interval_weeks": series.get("interval_weeks", 1),
            "repeat_label": "每周" if series.get("interval_weeks") == 1 else "隔周",
            "is_recurring": True,
            "source": "custom",
            "source_type": "recurring",
            "category": "重复待办",
            "action_ref": f"recurring:{series['id']}:{current_iso}",
            "done": status == "completed",
            "skipped": status == "skipped",
            "status": status,
            "commitment": "obligation",
            "active": not bool(series.get("deleted_at")),
            "completed_at": occ_meta.get("completed_at"),
            "skipped_at": occ_meta.get("skipped_at"),
            "series_created_at": series.get("created_at"),
        }

        # 只要在该范围内，或者后续需要它被排序
        occurrences.append(item)

        # 步进下一次
        rule = get_rule_for_date(current_due)
        step_days = int(rule.get("interval_weeks", 1)) * 7
        current_due = current_due + timedelta(days=step_days)
        count += 1

        if current_due > end_bound:
            break

    return occurrences


def get_homepage_item_for_series(series, today):
    """Select at most ONE occurrence for the homepage: earliest pending within window or overdue."""
    if series.get("deleted_at"):
        return None

    # 从首次截止开始展开到未来 60 天
    first_due = date.fromisoformat(series["first_due_date"])
    search_end = max(today + timedelta(days=60), first_due + timedelta(days=60))
    occs = expand_occurrences(series, first_due, search_end)

    # 过滤出所有尚未完成、未跳过的有效期次
    pending_occs = [o for o in occs if o["status"] == "pending"]
    if not pending_occs:
        return None

    # 按实际有效截止排序，取最早的一次
    pending_occs.sort(key=lambda o: (o["due_date"], o["original_due_date"]))
    earliest = pending_occs[0]

    earliest_due = date.fromisoformat(earliest["due_date"])
    # 首页准入条件：已逾期 或 距离今天不超过 7 天
    days_left = (earliest_due - today).days
    if earliest_due < today or days_left <= 7:
        return earliest

    return None


def get_homepage_items(username, today=None):
    """Retrieve all homepage-eligible recurring items for user (at most 1 per series)."""
    if today is None:
        today = datetime.now(CST).date()
    store = load_store(username)
    items = []
    for s in store.get("series", []):
        item = get_homepage_item_for_series(s, today)
        if item:
            items.append(item)
    return items


def get_range_occurrences(username, start_date, end_date):
    """Retrieve all occurrences for agenda / calendar within the range."""
    store = load_store(username)
    items = []
    for s in store.get("series", []):
        if s.get("deleted_at"):
            continue
        occs = expand_occurrences(s, start_date, end_date)
        for o in occs:
            d = date.fromisoformat(o["due_date"])
            if start_date <= d <= end_date:
                items.append(o)
    return items


def get_occurrence_by_ref(username, ref):
    """Retrieve a single occurrence by action ref (recurring:<series_id>:<orig_due_date>)."""
    if not ref or not ref.startswith("recurring:"):
        return None
    parts = ref.split(":", 2)
    if len(parts) != 3:
        return None
    _, series_id_str, orig_due_date = parts
    try:
        series_id = int(series_id_str)
        date.fromisoformat(orig_due_date)
    except (ValueError, TypeError):
        return None

    series = get_series(username, series_id)
    if not series or series.get("deleted_at"):
        return None

    occ_meta = (series.get("occurrences") or {}).get(orig_due_date, {})
    status = occ_meta.get("status", "pending")
    effective_due = occ_meta.get("due_date") or orig_due_date
    effective_title = occ_meta.get("title") or series["title"]
    effective_details = occ_meta.get("details") if occ_meta.get("details") is not None else series.get("details", "")

    return {
        "id": f"recurring_{series['id']}_{orig_due_date}",
        "series_id": series["id"],
        "original_due_date": orig_due_date,
        "due_date": effective_due,
        "due_str": effective_due,
        "due_ts": f"{effective_due}T23:59:59",
        "title": effective_title,
        "details": effective_details,
        "interval_weeks": series.get("interval_weeks", 1),
        "repeat_label": "每周" if series.get("interval_weeks") == 1 else "隔周",
        "is_recurring": True,
        "source": "recurring",
        "source_type": "recurring",
        "category": "重复待办",
        "ref": ref,
        "action_ref": ref,
        "done": status == "completed",
        "skipped": status == "skipped",
        "status": status,
        "commitment": "obligation",
        "active": not bool(series.get("deleted_at")),
        "editable": True,
        "deletable": True,
        "can_complete": True,
        "completed_at": occ_meta.get("completed_at"),
        "skipped_at": occ_meta.get("skipped_at"),
        "updated_at": occ_meta.get("updated_at") or series.get("updated_at"),
        "created_at": series.get("created_at"),
    }

