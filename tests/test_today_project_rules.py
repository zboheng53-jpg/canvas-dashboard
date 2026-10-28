"""Project visibility and next actions share dates, not platform classifications."""
from datetime import date, datetime, timedelta
from itertools import count

import pytest

import agent_auth
import app as dashboard
import project_store
import schedule_store
from routes import agent as agent_routes
from routes import planning as planning_routes
from services import workspace as workspace_service
from test_action_workspace import create_project, workspace


pytestmark = [pytest.mark.now("2026-10-28T12:00:00+08:00"), pytest.mark.usefixtures("project_clock")]


@pytest.fixture
def project_clock(monkeypatch, test_now):
    """Keep all projections on one Shanghai day while writes get unique versions."""
    clock = {"now": test_now}
    ticks = count()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"] + timedelta(microseconds=next(ticks))
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return clock["now"].date()

    for module in (dashboard, workspace_service, planning_routes, agent_routes, project_store):
        monkeypatch.setattr(module, "datetime", FixedDateTime)
    monkeypatch.setattr(project_store, "date", FixedDate)
    return clock


def _task(project, name, **fields):
    return project_store.create_task("alice", project["id"], {"name": name, **fields})


def _items(client):
    response = client.get("/api/projects/todos")
    assert response.status_code == 200
    return response.get_json()["items"]


def _ref(project, task):
    return f"project:{project['id']}:{task['id']}"


def _schedule(project, task, target="2026-10-28", hour="10:00", **fields):
    return schedule_store.create_item("alice", "one_off", {
        "title": task["name"], "action_ref": _ref(project, task),
        "date": target, "start_time": hour, "end_time": hour[:2] + ":30", **fields,
    })


def test_project_todo_admission_deduplicates_all_reasons_and_matches_agent(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    missed = _task(project, "原计划未完成", planned_on="2026-10-27", due_date="2026-11-03")
    today = _task(project, "今天计划", planned_on="2026-10-28")
    due = _task(project, "今天截止", due_date="2026-10-28", planned_on="2026-10-29")
    overdue = _task(project, "真实逾期", due_date="2026-10-26", planned_on="2026-10-27")
    _task(project, "未来任务", due_date="2026-11-03", planned_on="2026-10-29", commitment="obligation")
    _task(project, "无日期责任", commitment="obligation")
    scheduled = _task(project, "仅有今天时间块")
    _schedule(project, scheduled)
    _schedule(project, scheduled, hour="14:00")
    _schedule(project, overdue, hour="16:00")
    items = _items(client)
    expected = {t["id"] for t in (missed, today, due, overdue, scheduled)}
    assert {item["task_id"] for item in items} == expected
    assert len(items) == len(expected)
    old = next(item for item in items if item["task_id"] == missed["id"])
    assert old["missed_plan"] and old["is_today"]
    assert old["planned_on"] == "2026-10-27" and old["due_date"] == "2026-11-03"
    assert len(next(item for item in items if item["task_id"] == scheduled["id"])["occurrences"]) == 2
    token = agent_auth.create_token("alice", scopes=["read"])
    agent_items = client.get("/api/agent/v1/todos?source=project", headers={"Authorization": f"Bearer {token}"}).get_json()["todos"]
    assert len(agent_items) == len(expected)
    assert {item["ref"] for item in agent_items} == {_ref(project, task) for task in (missed, today, due, overdue, scheduled)}
    agent_old = next(item for item in agent_items if item["ref"] == _ref(project, missed))
    assert agent_old["due_date"] == "2026-11-03" and agent_old["missed_plan"]


@pytest.mark.parametrize("future_kind", ["one_off", "recurring", "far_future"])
def test_future_arrangements_never_silence_missed_plans(workspace, project_clock, future_kind):
    client, headers = workspace
    project = create_project(client, headers)
    task = _task(project, "补做期中练习", planned_on="2026-10-27", due_date="2026-11-03")
    if future_kind == "recurring":
        schedule_store.create_item("alice", "recurring", {
            "title": task["name"], "action_ref": _ref(project, task), "weekday": 3,
            "start_date": "2026-10-29", "start_time": "18:00", "end_time": "18:30", "enabled": True,
        })
    else:
        _schedule(project, task, "2026-11-25" if future_kind == "far_future" else "2026-10-29")
    for _ in range(2):
        items = _items(client)
        assert len(items) == 1 and items[0]["missed_plan"]
        assert items[0]["due_date"] == "2026-11-03"
        project_clock["now"] += timedelta(days=1)
    project_store.update_task("alice", project["id"], task["id"], {"planned_on": "2026-11-02"})
    assert _items(client) == []


def test_completed_time_blocks_do_not_complete_or_hide_missed_step(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    missed = _task(project, "未完成的旧计划", planned_on="2026-10-27")
    scheduled_only = _task(project, "没有计划日期的练习")
    for task in (missed, scheduled_only):
        block = _schedule(project, task)
        response = client.put(f"/api/schedule/one-off/{block['id']}/occurrence", headers=headers,
                              json={"date": "2026-10-28", "done": True})
        assert response.status_code == 200
        assert client.get(f"/api/actions/{_ref(project, task)}").get_json()["action"]["done"] is False
    assert [item["task_id"] for item in _items(client)] == [missed["id"]]
    assert _items(client)[0]["missed_plan"]
    project_store.update_task("alice", project["id"], missed["id"], {"done": True})
    assert _items(client) == []


def test_future_calendar_actions_survive_todo_filter_and_inactive_project_drops_out(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    future_plan = _task(project, "未来练习", planned_on="2026-11-04", commitment="growth")
    future_due = _task(project, "未来提交", due_date="2026-11-05", commitment="obligation")
    assert _items(client) == []
    calendar = project_store.calendar_items("alice")
    assert {item["uid"] for item in calendar} == {
        f"project-task-{project['id']}-{task['id']}@canvas-dashboard" for task in (future_plan, future_due)
    }
    for task in (future_plan, future_due):
        assert client.get(f"/api/actions/{_ref(project, task)}").status_code == 200
    project_store.update_task("alice", project["id"], future_plan["id"], {"planned_on": "2026-10-27"})
    assert len(_items(client)) == 1
    project_store.archive_project("alice", project["id"])
    assert _items(client) == [] and project_store.calendar_items("alice") == []
    assert len(project_store.load_projects("alice")[0]["tasks"]) == 2


def test_next_step_uses_plan_date_then_group_order_and_keeps_manual_selection(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    current = _task(project, "当前步")
    group_a = project_store.create_group("alice", project["id"], "第一阶段")
    group_b = project_store.create_group("alice", project["id"], "第二阶段")
    later = _task(project, "晚一些", planned_on="2026-11-03", group_id=group_a["id"])
    same_b = _task(project, "同日后阶段", planned_on="2026-10-29", group_id=group_b["id"])
    same_a = _task(project, "同日前阶段", planned_on="2026-10-29", group_id=group_a["id"])
    undated = _task(project, "无日期步骤")

    def next_id():
        entry = client.get("/api/projects/overview").get_json()["active_projects"][0]
        return entry["next_action"]["id"] if entry["next_action"] else None

    assert next_id() == current["id"]
    project_store.update_task("alice", project["id"], current["id"], {"done": True})
    assert next_id() == same_a["id"]
    project_store.set_next_task("alice", project["id"], later["id"])
    project_store.update_task("alice", project["id"], current["id"], {"done": False})
    assert next_id() == later["id"]
    project_store.delete_task("alice", project["id"], later["id"])
    assert next_id() == same_a["id"]
    for expected in (same_a, same_b, current, undated):
        assert next_id() == expected["id"]
        project_store.update_task("alice", project["id"], expected["id"], {"done": True})
    assert next_id() is None
