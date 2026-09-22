"""Unit and API regression tests for cross-module linkage fixes (LINK-01 ~ LINK-09)."""
from datetime import date, timedelta
import json
import pytest

import agent_auth
import app as dashboard
import project_store
import recurring_todo_store
import schedule_store
import user_paths
import workspace_agenda


@pytest.fixture
def linkage_env(tmp_path, monkeypatch):
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard, "user_dir", user_paths.user_dir)
    monkeypatch.setattr(agent_auth, "user_dir", user_paths.user_dir)
    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})
    dashboard.app.config.update(TESTING=True)
    client = dashboard.app.test_client()
    with client.session_transaction() as session:
        session.update(username="alice", _csrf_token="csrf")
    headers = {"X-CSRF-Token": "csrf"}
    return client, headers


def test_link_02_recurring_exception_supports_date_change_and_cancel(linkage_env):
    """LINK-02: Recurring exception endpoint supports changing date and cancellation."""
    c, h = linkage_env
    item = schedule_store.create_item("alice", "recurring", {
        "title": "每周研讨",
        "weekday": 0,
        "start_date": "2026-09-14",
        "start_time": "14:00",
        "end_time": "15:00",
        "enabled": True,
    })
    # Mark occurrence done
    schedule_store.complete_occurrence("alice", "recurring", item["id"], "2026-09-14", True)

    # 1. Test changing occurrence date to a new date (2026-09-15)
    url = f"/api/schedule/recurring/{item['id']}/exception"
    res = c.post(url, headers=h, json={
        "date": "2026-09-14",
        "changes": {
            "title": "调至周二研讨",
            "date": "2026-09-15",
            "start_time": "15:00",
            "end_time": "16:00",
        }
    })
    assert res.status_code == 200, res.get_json()
    new_item = res.get_json()["item"]
    assert new_item["date"] == "2026-09-15"
    assert new_item["title"] == "调至周二研讨"
    assert new_item["occurrence_done"] is True

    # 2. Test cancel (cancellation skips the occurrence without creating one-off)
    res_cancel = c.post(url, headers=h, json={
        "date": "2026-09-21",
        "cancel": True,
    })
    assert res_cancel.status_code == 200
    updated_rec = schedule_store.load_items("alice")["recurring"][0]
    assert "2026-09-21" in updated_rec.get("skipped_dates", [])


def test_link_03_recurring_occurrence_by_ref_contract(linkage_env):
    """LINK-03: get_occurrence_by_ref returns ref, editable, and status flags."""
    client, headers = linkage_env
    series = recurring_todo_store.create_series("alice", {
        "title": "每周阅读",
        "first_due_date": "2026-09-14",
        "interval_weeks": 1,
    })
    ref = f"recurring:{series['id']}:2026-09-14"
    occ = recurring_todo_store.get_occurrence_by_ref("alice", ref)
    assert occ is not None
    assert occ["ref"] == ref
    assert occ["action_ref"] == ref
    assert occ["editable"] is True
    assert occ["can_complete"] is True
    assert occ["done"] is False

    # Complete via API and check ref response
    res = client.get(f"/api/actions/{ref}")
    assert res.status_code == 200
    action = res.get_json()["action"]
    assert action["ref"] == ref
    assert action["title"] == "每周阅读"


def test_link_03_platform_action_uncomplete(linkage_env):
    """LINK-03: PUT /api/actions/<ref> with done: False uncompletes platform item."""
    c, h = linkage_env
    cache = user_paths.user_dir("alice") / "canvas_cache.json"
    cache.write_text(json.dumps([{"id": 88, "title": "期末论文", "course": "文学", "due_ts": "2026-09-20T23:59:00Z"}]), encoding="utf-8")
    ref = "canvas:88"

    # Complete
    res1 = c.put(f"/api/actions/{ref}", headers=h, json={"done": True})
    assert res1.status_code == 200
    assert c.get(f"/api/actions/{ref}").get_json()["action"]["done"] is True

    # Uncomplete
    res2 = c.put(f"/api/actions/{ref}", headers=h, json={"done": False})
    assert res2.status_code == 200
    assert c.get(f"/api/actions/{ref}").get_json()["action"]["done"] is False


def test_link_04_deleted_custom_todo_excluded_from_agenda(linkage_env):
    """LINK-04: Deleted or completed custom todo is handled cleanly in agenda."""
    c, h = linkage_env
    # Create custom todo
    res = c.post("/api/custom/todos", headers=h, json={"text": "写周报", "due_date": "2026-09-14"})
    todo = res.get_json()["todo"]
    ref = todo["ref"]

    # Schedule it
    sch_res = c.post("/api/schedule/one-off", headers=h, json={
        "action_ref": ref,
        "date": "2026-09-14",
        "start_time": "10:00",
        "end_time": "11:00",
    })
    assert sch_res.status_code == 200

    agenda_before = c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()
    assert len(agenda_before["days"][0]["timed"]) == 1
    assert agenda_before["days"][0]["timed"][0]["title"] == "写周报"

    # Delete the custom todo
    c.delete(f"/api/custom/todos/{todo['id']}", headers=h)

    # Agenda should no longer show the deleted item as active timed schedule
    agenda_after = c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()
    assert len(agenda_after["days"][0]["timed"]) == 0


def test_link_05_past_schedule_in_focus_previous(linkage_env):
    """LINK-05: Past schedule item on project action appears in focus.previous."""
    c, h = linkage_env
    p = c.post("/api/projects", json={"name": "毕业设计"}, headers=h).get_json()["project"]
    task = project_store.create_task("alice", p["id"], {"name": "开题报告大纲", "commitment": "growth"})
    ref = f"project:{p['id']}:{task['id']}"

    # Schedule on a past day
    c.post("/api/schedule/one-off", headers=h, json={
        "action_ref": ref,
        "date": "2026-09-10",
        "start_time": "09:00",
        "end_time": "10:00",
    })

    # Today is after the schedule date
    focus = c.get("/api/actions/focus").get_json()
    prev_titles = [item["title"] for item in focus.get("previous", [])]
    assert "开题报告大纲" in prev_titles


def test_link_06_agent_todos_aligns_with_focus_today(linkage_env):
    """LINK-06: Agent GET /api/agent/v1/todos includes today's growth tasks."""
    c, h = linkage_env
    token = agent_auth.create_token("alice")
    bearer = {"Authorization": f"Bearer {token}"}
    today_iso = date.today().isoformat()

    p = c.post("/api/projects", json={"name": "考研复习"}, headers=h).get_json()["project"]
    task = c.post(f"/api/projects/{p['id']}/tasks", headers=h, json={
        "name": "背诵考研单词",
        "commitment": "growth",
        "planned_on": today_iso,
    }).get_json()["task"]

    agent_todos = c.get("/api/agent/v1/todos", headers=bearer).get_json()["todos"]
    titles = [t["title"] for t in agent_todos]
    assert "背诵考研单词" in titles


def test_link_08_schedule_details_and_action_details_decoupled(linkage_env):
    """LINK-08: Schedule details and action details are preserved separately."""
    c, h = linkage_env
    p = c.post("/api/projects", json={"name": "竞赛"}, headers=h).get_json()["project"]
    task = project_store.create_task("alice", p["id"], {
        "name": "撰写文档",
        "details": "请参考比赛官网模版要求编写。"
    })
    ref = f"project:{p['id']}:{task['id']}"

    c.post("/api/schedule/one-off", headers=h, json={
        "action_ref": ref,
        "date": "2026-09-14",
        "start_time": "14:00",
        "end_time": "15:00",
        "details": "地点：图书馆研讨室二楼",
    })

    agenda = c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()
    timed_item = agenda["days"][0]["timed"][0]
    assert timed_item["schedule_details"] == "地点：图书馆研讨室二楼"
    assert timed_item["action_details"] == "请参考比赛官网模版要求编写。"
