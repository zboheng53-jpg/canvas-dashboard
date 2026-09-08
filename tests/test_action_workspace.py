import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
import app as dashboard
import agent_auth
import project_store
import schedule_store
import user_paths


@pytest.fixture
def workspace(tmp_path, monkeypatch):
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


def create_project(client, headers):
    return client.post("/api/projects", json={"name": "英语提升"}, headers=headers).get_json()["project"]


def test_growth_plan_and_undated_obligation_have_distinct_views(workspace):
    c, h = workspace
    p = create_project(c, h)
    growth = c.post(f"/api/projects/{p['id']}/tasks", json={"name": "练习听力", "planned_on": "2026-09-14", "details": "先听音频，再核对原文。"}, headers=h).get_json()["task"]
    hard = c.post(f"/api/projects/{p['id']}/tasks", json={"name": "核实报名资格", "commitment": "obligation"}, headers=h).get_json()["task"]
    assert growth["commitment"] == "growth" and growth["due_date"] is None
    assert [a["title"] for a in c.get("/api/projects/todos").get_json()["items"]] == [hard["name"]]
    agenda = c.get("/api/agenda?start=2026-09-14&end=2026-09-16").get_json()
    assert agenda["days"][0]["planned"][0]["title"] == growth["name"]
    assert agenda["days"][0]["deadlines"] == []
    assert "sync_status" in agenda
    assert {a["title"] for a in agenda["unscheduled"]} == {growth["name"], hard["name"]}


def test_schedule_ref_tracks_rename_completion_and_cancel_keeps_action(workspace):
    c, h = workspace
    p = create_project(c, h)
    task = project_store.create_task("alice", p["id"], {"name": "练习听力", "planned_on": "2026-09-14"})
    ref = f"project:{p['id']}:{task['id']}"
    item = c.post("/api/schedule/one-off", json={"action_ref": ref, "date": "2026-09-14", "start_time": "19:00", "end_time": "19:25"}, headers=h).get_json()["item"]
    c.put(f"/api/actions/{ref}", json={"title": "复习听力错题", "expected_updated_at": task["updated_at"]}, headers=h)
    agenda = c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()
    assert agenda["days"][0]["timed"][0]["title"] == "复习听力错题"
    assert agenda["days"][0]["planned"] == []
    c.put(f"/api/actions/{ref}", json={"done": True}, headers=h)
    assert c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()["days"][0]["timed"][0]["done"] is True
    c.delete(f"/api/schedule/one-off/{item['id']}", headers=h)
    assert c.get(f"/api/actions/{ref}").get_json()["action"]["done"] is True
    c.put(f"/api/actions/{ref}", json={"done": False}, headers=h)
    assert c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()["days"][0]["planned"][0]["ref"] == ref


def test_recurrence_completion_is_per_occurrence(workspace):
    c, h = workspace
    p = create_project(c, h)
    task = project_store.create_task("alice", p["id"], {"name": "每周听力练习"})
    ref = f"project:{p['id']}:{task['id']}"
    item = c.post("/api/schedule/recurring", json={"action_ref": ref, "weekday": 0, "start_date": "2026-09-14", "end_date": "2026-09-28", "start_time": "19:00", "end_time": "19:25"}, headers=h).get_json()["item"]
    result = c.put(f"/api/schedule/recurring/{item['id']}/occurrence", json={"date": "2026-09-14", "done": True}, headers=h)
    assert result.status_code == 200
    agenda = c.get("/api/agenda?start=2026-09-14&end=2026-09-21").get_json()
    assert agenda["days"][0]["timed"][0]["occurrence_done"] is True
    assert agenda["days"][7]["timed"][0]["occurrence_done"] is False
    assert c.get(f"/api/actions/{ref}").get_json()["action"]["done"] is False
    assert c.put(f"/api/schedule/recurring/{item['id']}/occurrence", json={"date": "2026-09-15", "done": True}, headers=h).status_code == 404


def test_legacy_title_and_due_are_preserved_until_explicit_edit(workspace):
    c, h = workspace
    path = user_paths.user_dir("alice") / "projects.json"
    long_title = "听力练习及具体步骤与完成标准；" * 8
    path.write_text(json.dumps({"version": 2, "projects": [{"id": 1, "name": "英语", "tasks": [{"id": 7, "name": long_title, "due_date": "2026-09-14"}]}]}, ensure_ascii=False), encoding="utf-8")
    action = c.get("/api/actions/project:1:7").get_json()["action"]
    assert action["commitment"] == "legacy"
    assert c.get("/api/projects/todos").get_json()["count"] == 1
    c.put("/api/actions/project:1:7", json={"title": "完成听力练习", "details": long_title, "commitment": "growth", "planned_on": "2026-09-14", "due_date": None}, headers=h)
    action = c.get("/api/actions/project:1:7").get_json()["action"]
    assert action["original_name"] == long_title and action["id"] == 7
    assert action["due_date"] is None and action["planned_on"] == "2026-09-14"
    assert c.get("/api/projects/todos").get_json()["count"] == 0


def test_idempotency_versions_and_deleted_ids_do_not_rebind(workspace):
    c, h = workspace
    p = create_project(c, h)
    payload = {"name": "练习听力", "request_id": "listen-1"}
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: project_store.create_task("alice", p["id"], payload), range(2)))
    assert results[0]["id"] == results[1]["id"]
    url = f"/api/projects/{p['id']}/tasks"
    assert c.post(url, json={**payload, "name": "不同内容"}, headers=h).status_code == 409
    task = results[0]; ref = f"project:{p['id']}:{task['id']}"
    assert c.put(f"/api/actions/{ref}", json={"details": "新说明", "expected_updated_at": task["updated_at"]}, headers=h).status_code == 200
    assert c.put(f"/api/actions/{ref}", json={"details": "旧对话", "expected_updated_at": task["updated_at"]}, headers=h).status_code == 409
    c.delete(f"{url}/{task['id']}", headers=h)
    newer = c.post(url, json={"name": "新的行动"}, headers=h).get_json()["task"]
    assert newer["id"] > task["id"]
    assert c.get(f"/api/actions/{ref}").status_code == 404


def test_agent_uses_same_actions_aggregate_and_account_boundary(workspace):
    c, h = workspace
    token = agent_auth.create_token("alice")
    bearer = {"Authorization": f"Bearer {token}"}
    p = create_project(c, h)
    res = c.post(f"/api/agent/v1/projects/{p['id']}/tasks", headers=bearer, json={"name": "完成听力练习", "commitment": "growth", "planned_on": "2026-09-14", "request_id": "agent-task"})
    assert res.status_code == 201
    ref = res.get_json()["ref"]
    assert c.get(f"/api/agent/v1/actions/{ref}", headers=bearer).get_json()["action"]["title"] == "完成听力练习"
    assert c.get("/api/agent/v1/agenda?start=2026-09-14&end=2026-09-14", headers=bearer).get_json()["days"] == c.get("/api/agenda?start=2026-09-14&end=2026-09-14").get_json()["days"]
    assert c.get("/api/agent/v1/todos", headers=bearer).get_json()["count"] == 0
    with c.session_transaction() as sess:
        sess["username"] = "bob"
    assert c.get(f"/api/actions/{ref}").status_code == 404
    assert c.get("/api/agent/v1/actions").status_code == 401


def test_bad_titles_dates_and_references_do_not_write(workspace):
    c, h = workspace
    p = create_project(c, h)
    url = f"/api/projects/{p['id']}/tasks"
    assert c.post(url, headers=h, json={"name": "文" * 41}).status_code == 400
    assert c.post(url, headers=h, json={"name": "听力", "planned_on": "2026-02-30"}).status_code == 400
    assert c.post(url, headers=h, json={"name": ["听力"]}).status_code == 400
    assert project_store.load_projects("alice")[0]["tasks"] == []
    assert c.post("/api/schedule/one-off", headers=h, json={"action_ref": "project:99:99", "date": "2026-09-14", "start_time": "25:00", "end_time": "26:00"}).status_code == 400
    assert c.get("/api/agenda?start=2026-09-30&end=2026-09-01").status_code == 400


def test_single_occurrence_edit_is_atomic_and_retry_safe(workspace):
    c, h = workspace
    recurring = schedule_store.create_item("alice", "recurring", {"title": "每周讨论", "weekday": 0, "start_date": "2026-09-14", "start_time": "19:00", "end_time": "20:00", "enabled": True})
    url = f"/api/schedule/recurring/{recurring['id']}/exception"
    bad = {"date": "2026-09-14", "changes": {"title": "讨论", "start_time": "25:00", "end_time": "26:00"}}
    assert c.post(url, headers=h, json=bad).status_code == 400
    assert not schedule_store.load_items("alice")["recurring"][0].get("skipped_dates")
    recurring = schedule_store.complete_occurrence("alice", "recurring", recurring["id"], "2026-09-14", True)
    payload = {"date": "2026-09-14", "expected_updated_at": recurring["updated_at"],
               "changes": {"title": "本次讨论", "start_time": "20:00", "end_time": "21:00", "request_id": "exception-1"}}
    first = c.post(url, headers=h, json=payload)
    second = c.post(url, headers=h, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.get_json()["item"]["id"] == second.get_json()["item"]["id"]
    agenda = c.get("/api/agenda?start=2026-09-14&end=2026-09-21").get_json()
    assert [e["title"] for e in agenda["days"][0]["timed"]] == ["本次讨论"]
    assert [e["title"] for e in agenda["days"][7]["timed"]] == ["每周讨论"]
    assert agenda["days"][0]["timed"][0]["occurrence_done"] is True
    assert agenda["days"][7]["timed"][0]["occurrence_done"] is False


def test_schedule_partial_edit_preserves_link_and_retry_after_rename(workspace):
    c, h = workspace
    p = create_project(c, h)
    task = project_store.create_task("alice", p["id"], {"name": "听力"})
    ref = f"project:{p['id']}:{task['id']}"
    payload = {"action_ref": ref, "date": "2026-09-14", "start_time": "19:00", "end_time": "19:25", "request_id": "block-1"}
    item = c.post("/api/schedule/one-off", headers=h, json=payload).get_json()["item"]
    c.put(f"/api/actions/{ref}", headers=h, json={"title": "听力复盘"})
    assert c.post("/api/schedule/one-off", headers=h, json=payload).get_json()["item"]["id"] == item["id"]
    result = c.put(f"/api/schedule/one-off/{item['id']}", headers=h, json={"start_time": "19:05", "expected_updated_at": item["updated_at"]})
    assert result.status_code == 200
    assert result.get_json()["item"]["action_ref"] == ref


def test_platform_deadline_uses_shanghai_day_and_preserves_cache(workspace):
    c, h = workspace
    cache = user_paths.user_dir("alice") / "canvas_cache.json"
    raw = [{"id": 42, "title": "学校原始作业标题", "course": "自动控制", "due_ts": "2026-09-14T18:30:00Z", "url": "https://school.example/task/42"}]
    cache.write_text(json.dumps(raw), encoding="utf-8")
    before = cache.read_bytes()
    day = c.get("/api/agenda?start=2026-09-15&end=2026-09-15").get_json()["days"][0]
    assert day["deadlines"][0]["deadline_time"] == "02:30"
    assert day["deadlines"][0]["action_ref"] == "canvas:42"
    assert c.put("/api/actions/canvas:42", headers=h, json={"done": True}).status_code == 200
    assert c.get("/api/actions/canvas:42").get_json()["action"]["done"] is True
    assert cache.read_bytes() == before
