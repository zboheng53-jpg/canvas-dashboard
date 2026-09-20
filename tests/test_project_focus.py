"""Project focus and reversible cleanup share the production stores and API."""
from datetime import timedelta
from unittest.mock import Mock
import json
import pytest
import app as dashboard
import project_store
import schedule_store
import agent_mcp
from test_action_workspace import workspace, create_project


def task(project, name="练习听力", **fields):
    return project_store.create_task("alice", project["id"], {"name": name, **fields})


def test_focus_deduplicates_today_and_separates_old_plans(workspace):
    c, h = workspace
    p = create_project(c, h)
    day = dashboard.datetime.now(dashboard.CST).date()
    a = task(p, planned_on=day.isoformat(), due_date=day.isoformat(), is_next_action=True)
    ref = f"project:{p['id']}:{a['id']}"
    for hour in (10, 14):
        schedule_store.create_item("alice", "one_off", {"title": a["name"], "action_ref": ref, "date": day.isoformat(), "start_time": f"{hour}:00", "end_time": f"{hour}:30"})
    old = task(p, "旧计划", planned_on=(day-timedelta(days=1)).isoformat())
    overdue = task(p, "真实承诺", due_date=(day-timedelta(days=1)).isoformat(), commitment="obligation")
    data = c.get("/api/actions/focus").get_json()
    assert [a["ref"] for a in data["today"]] == [ref]
    assert len(data["today"][0]["occurrences"]) == 2
    assert [a["task_id"] for a in data["previous"]] == [old["id"]]
    assert [a["task_id"] for a in data["overdue"]] == [overdue["id"]]
    assert not data["candidates"]
    c.put(f"/api/actions/{ref}", json={"done": True, "expected_updated_at": a["updated_at"]}, headers=h)
    assert not c.get("/api/actions/focus").get_json()["today"]


def test_focus_candidates_do_not_assign_dates_or_repeat_completed_occurrences(workspace):
    c, h = workspace
    p = create_project(c, h)
    day = dashboard.datetime.now(dashboard.CST).date()
    a = task(p, is_next_action=True)
    ref = f"project:{p['id']}:{a['id']}"
    assert c.get("/api/actions/focus").get_json()["candidates"][0]["planned_on"] is None
    item = schedule_store.create_item("alice", "recurring", {"title": a["name"], "action_ref": ref, "weekday": day.weekday(), "start_date": day.isoformat(), "end_date": (day+timedelta(days=14)).isoformat(), "start_time": "19:00", "end_time": "19:30"})
    c.put(f"/api/schedule/recurring/{item['id']}/occurrence", json={"date": day.isoformat(), "done": True}, headers=h)
    data = c.get("/api/actions/focus").get_json()
    assert not data["today"] and not data["candidates"]
    assert not c.get(f"/api/actions/{ref}").get_json()["action"]["done"]


@pytest.mark.parametrize("operation", ["archive", "complete", "delete"])
def test_inactive_project_filters_linked_agenda_and_calendar_without_deleting(workspace, operation):
    c, h = workspace
    p = create_project(c, h)
    day = dashboard.datetime.now(dashboard.CST).date().isoformat()
    a = task(p, planned_on=day, is_next_action=True)
    ref = f"project:{p['id']}:{a['id']}"
    item = schedule_store.create_item("alice", "one_off", {"title": a["name"], "action_ref": ref, "date": day, "start_time": "19:00", "end_time": "19:30"})
    project_store.set_main_project("alice", p["id"])
    if operation == "delete":
        r = c.delete(f"/api/projects/{p['id']}", headers=h)
    else:
        r = c.post(f"/api/projects/{p['id']}/{operation}", headers=h)
    assert r.status_code == 200
    agenda = c.get(f"/api/agenda?start={day}&end={day}").get_json()
    assert not agenda["days"][0]["timed"] and not agenda["days"][0]["planned"]
    assert not c.get("/api/actions/focus").get_json()["today"]
    assert not any(i["uid"] == f"schedule-oneoff-{item['id']}@canvas-dashboard" for i in dashboard._calendar_items("alice", category="schedule"))
    assert schedule_store.load_items("alice")["one_off"][0]["action_ref"] == ref
    c.post(f"/api/projects/{p['id']}/{'restore' if operation == 'delete' else 'reopen'}", headers=h)
    assert c.get(f"/api/agenda?start={day}&end={day}").get_json()["days"][0]["timed"][0]["action_ref"] == ref
    assert project_store.load_state("alice")["main_project_id"] is None
    assert project_store.calendar_items("alice")[0]["uid"] == f"project-task-{p['id']}-{a['id']}@canvas-dashboard"


def test_materials_conversion_conflict_replay_restore_and_reorder(workspace):
    c, h = workspace
    p = create_project(c, h)
    a = task(p, details="保留完整方案", is_next_action=True)
    b = task(p, "另一个明确行动")
    p = project_store.load_projects("alice")[0]
    path = f"/api/projects/{p['id']}/tasks/{a['id']}"
    payload = {"expected_updated_at": a["updated_at"], "expected_project_updated_at": "old"}
    assert c.post(path+"/to-materials", json=payload, headers=h).status_code == 409
    assert len(project_store.load_projects("alice")[0]["tasks"]) == 2
    payload["expected_project_updated_at"] = p["updated_at"]
    assert c.post(path+"/to-materials", json=payload, headers=h).status_code == 200
    assert c.post(path+"/to-materials", json=payload, headers=h).status_code == 200
    current = project_store.load_projects("alice")[0]
    assert current["materials"].count("保留完整方案") == 1
    assert f"project:{p['id']}:{a['id']}" in current["materials"]
    assert [t["id"] for t in current["tasks"]] == [b["id"]]
    assert project_store.reorder_tasks("alice", p["id"], [{"id":b["id"], "group_id":None}])
    recycled = c.get("/api/projects/trash").get_json()["tasks"][0]
    assert recycled["details"] == "保留完整方案" and not recycled["done"]
    assert c.post(path+"/restore", json={"expected_updated_at":recycled["updated_at"]}, headers=h).status_code == 200
    restored = next(t for t in project_store.load_projects("alice")[0]["tasks"] if t["id"] == a["id"])
    assert not restored["is_next_action"] and restored["details"] == a["details"]
    assert project_store.load_projects("bob", include_deleted=True) == []


def test_materials_overflow_preserves_task_and_project(workspace):
    c, h = workspace
    p = create_project(c, h)
    project_store.update_project("alice", p["id"], {"materials":"x"*20000})
    a = task(p)
    p = project_store.load_projects("alice")[0]
    response = c.post(f"/api/projects/{p['id']}/tasks/{a['id']}/to-materials", json={"expected_updated_at":a["updated_at"], "expected_project_updated_at":p["updated_at"]}, headers=h)
    assert response.status_code == 400
    assert len(project_store.load_projects("alice")[0]["tasks"]) == 1
    assert project_store.load_projects("alice")[0]["materials"] == "x"*20000


def test_mcp_projects_preserve_context_and_management_versions():
    client = Mock()
    full = {"ok":True,"projects":[{"id":1,"updated_at":"v1","materials":"背景","tasks":[{"id":2,"updated_at":"v2"}]}]}
    client.request.return_value = full
    assert json.loads(agent_mcp.handle_tool_call(client,"get_projects",{})) == full
    agent_mcp.handle_tool_call(client,"manage_project_record",{"project_id":1,"task_id":2,"operation":"to-materials","expected_updated_at":"v2","expected_project_updated_at":"v1"})
    client.request.assert_called_with("/api/agent/v1/projects/1/tasks/2/to-materials",method="POST",data={"expected_updated_at":"v2","expected_project_updated_at":"v1"})


def test_exported_rules_match_and_agent_auth_is_required(workspace):
    import io
    import zipfile
    import agent_auth
    c, h = workspace
    for endpoint in ("/api/agent/v1/actions/focus", "/api/agent/v1/projects/trash"):
        assert c.get(endpoint).status_code == 401
    token = agent_auth.create_token("alice")
    auth = {"Authorization": f"Bearer {token}"}
    assert c.get("/api/agent/v1/actions/focus", headers=auth).status_code == 200
    p = create_project(c,h)
    a = task(p)
    # Explicit multi-step requests remain possible: there is no server-side quota.
    assert c.post(f"/api/agent/v1/projects/{p['id']}/tasks",json={"name":"另一条明确行动","request_id":"explicit-second"},headers=auth).status_code == 201
    assert c.post(f"/api/agent/v1/projects/{p['id']}/tasks/{a['id']}/delete",json={"expected_updated_at":a["updated_at"]},headers=auth).status_code == 200
    assert c.get("/api/agent/v1/projects/trash",headers=auth).get_json()["tasks"][0]["id"] == a["id"]
    bundle = c.get("/api/agent/export/skill-bundle.zip")
    with zipfile.ZipFile(io.BytesIO(bundle.data)) as z:
        skill = z.read("SKILL.md").decode("utf-8")
    assert agent_mcp.WRITING_RULES in skill
    # The installed MCP's initialize response must use the same rules; source bundle is inspectable.
    bundle = c.get("/api/agent/export/mcp-bundle.zip")
    with zipfile.ZipFile(io.BytesIO(bundle.data)) as z:
        source = next(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith("canvas_mcp.py"))
    assert "get_project_focus" in source and "manage_project_record" in source
