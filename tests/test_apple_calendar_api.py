import json

import pytest

import app as dashboard_app
import apple_calendar
import project_store
import user_paths
import zhihuishu_store


@pytest.fixture
def calendar_client(tmp_path, monkeypatch):
    def resolve_user_dir(username):
        path = tmp_path / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", resolve_user_dir)
    monkeypatch.setattr(apple_calendar, "DATA_DIR", tmp_path)
    monkeypatch.setattr(apple_calendar, "user_dir", resolve_user_dir)
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app.settings, "APPLE_CALENDAR_ENABLED", True)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client, resolve_user_dir


def test_calendar_subscription_reads_only_active_cached_tasks(calendar_client, monkeypatch):
    client, user_dir = calendar_client
    user_dir("alice").joinpath("custom_todos.json").write_text(
        json.dumps([
            {
                "id": 1,
                "text": "Custom due date",
                "due_date": "2099-07-11",
                "done": False,
                "subtasks": [
                    {"id": 1, "text": "Active subtask", "due_date": "2099-07-13", "done": False},
                    {"id": 2, "text": "Completed subtask", "due_date": "2099-07-13", "done": True},
                    {"id": 3, "text": "Undated subtask", "done": False},
                ],
            },
            {"id": 2, "text": "Completed custom", "due_date": "2099-07-11", "done": True},
            {
                "id": 3,
                "text": "Undated parent",
                "due_date": None,
                "done": False,
                "subtasks": [
                    {"id": 1, "text": "Subtask without parent date", "due_date": "2099-07-14", "done": False},
                ],
            },
            {
                "id": 4,
                "text": "Completed parent",
                "due_date": None,
                "done": True,
                "subtasks": [
                    {"id": 1, "text": "Subtask of completed parent", "due_date": "2099-07-15", "done": False},
                ],
            },
        ]),
        encoding="utf-8",
    )
    user_dir("alice").joinpath("canvas_cache.json").write_text(
        json.dumps([
            {"id": 11, "title": "Canvas visible", "due_ts": "2099-07-12T09:00:00+08:00"},
            {"id": 12, "title": "Canvas hidden", "due_ts": "2099-07-12T09:00:00+08:00"},
        ]),
        encoding="utf-8",
    )
    user_dir("alice").joinpath("canvas_state.json").write_text('{"hidden": [12], "highlighted": [], "deleted": []}', encoding="utf-8")
    user_dir("alice").joinpath("haoke_cache.json").write_text(
        json.dumps([{"id": 21, "title": "Haoke visible", "due_ts": "2099-07-12T10:00:00+08:00"}]),
        encoding="utf-8",
    )
    user_dir("alice").joinpath("zhixuemeng_cache.json").write_text(
        json.dumps({"items": [{"id": "zxm-31", "title": "Zxm visible", "due_ts": "2099-07-12T11:00:00+08:00"}]}),
        encoding="utf-8",
    )
    zhihuishu_store.save_cache("alice", [{"id": "zhs-41", "title": "Zhs visible", "due_ts": "2099-07-12T12:00:00+08:00"}])
    project = project_store.create_project(
        "alice",
        {"name": "Python 学习", "due_date": "2099-09-01"},
    )
    project_task = project_store.create_task(
        "alice",
        project["id"],
        {"name": "NumPy 数组练习", "due_date": "2099-08-02"},
    )

    monkeypatch.setattr(dashboard_app, "fetch_canvas_planner", lambda username: pytest.fail("calendar subscription must not fetch Canvas"))
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: pytest.fail("calendar subscription must not fetch 好课"))
    monkeypatch.setattr(dashboard_app, "fetch_zxm_assignments", lambda username: pytest.fail("calendar subscription must not fetch 智学盟"))

    created = client.post("/api/apple-calendar/subscription", headers=client.csrf_headers)

    assert created.status_code == 200
    path = created.get_json()["path"]

    with dashboard_app.app.test_client() as anonymous_client:
        response = anonymous_client.get(path)

    assert response.status_code == 200
    assert response.content_type == "text/calendar; charset=utf-8"
    body = response.get_data(as_text=True)
    for title in (
        "Custom due date",
        "Active subtask",
        "Subtask without parent date",
        "Canvas visible",
        "Haoke visible",
        "Zxm visible",
        "Zhs visible",
        "NumPy 数组练习 · Python 学习",
        "项目截止 · Python 学习",
    ):
        assert title in body
    assert "DTSTART;VALUE=DATE:20990711" in body
    assert "DTSTART;VALUE=DATE:20990713" in body
    assert "DTSTART;VALUE=DATE:20990714" in body
    assert "UID:custom-1-subtask-1@canvas-dashboard" in body
    assert "UID:custom-3-subtask-1@canvas-dashboard" in body
    assert f"UID:project-task-{project['id']}-{project_task['id']}@canvas-dashboard" in body
    assert f"UID:project-due-{project['id']}@canvas-dashboard" in body
    assert "Completed custom" not in body
    assert "Completed subtask" not in body
    assert "Undated subtask" not in body
    assert "Subtask of completed parent" not in body
    assert "Canvas hidden" not in body
    assert "alice" not in body


def test_calendar_subscription_token_is_revocable(calendar_client):
    client, _ = calendar_client

    created = client.post("/api/apple-calendar/subscription", headers=client.csrf_headers)
    assert created.status_code == 200
    path = created.get_json()["path"]

    revoked = client.delete("/api/apple-calendar/subscription", headers=client.csrf_headers)
    assert revoked.status_code == 200
    assert revoked.get_json() == {"ok": True}

    with dashboard_app.app.test_client() as anonymous_client:
        assert anonymous_client.get(path).status_code == 404
        assert anonymous_client.get("/calendar/not-a-token.ics").status_code == 404


def test_project_calendar_events_keep_uids_through_renames_and_follow_status(calendar_client):
    client, _ = calendar_client
    project = project_store.create_project(
        "alice",
        {"name": "Python 学习", "due_date": "2099-09-01"},
    )
    task = project_store.create_task(
        "alice",
        project["id"],
        {"name": "NumPy 练习", "due_date": "2099-08-02"},
    )
    bob = project_store.create_project(
        "bob",
        {"name": "Bob 私有项目", "due_date": "2099-09-03"},
    )
    project_store.create_task(
        "bob",
        bob["id"],
        {"name": "Bob 私有任务", "due_date": "2099-08-04"},
    )
    path = client.post(
        "/api/apple-calendar/subscription",
        headers=client.csrf_headers,
    ).get_json()["path"]

    with dashboard_app.app.test_client() as anonymous:
        before = anonymous.get(path).get_data(as_text=True)

    task_uid = f"UID:project-task-{project['id']}-{task['id']}@canvas-dashboard"
    due_uid = f"UID:project-due-{project['id']}@canvas-dashboard"
    assert before.count(task_uid) == 1
    assert before.count(due_uid) == 1
    assert "Bob 私有项目" not in before
    assert "Bob 私有任务" not in before

    client.put(
        f"/api/projects/{project['id']}",
        json={"name": "Python 数据处理", "due_date": "2099-09-05"},
        headers=client.csrf_headers,
    )
    client.put(
        f"/api/projects/{project['id']}/tasks/{task['id']}",
        json={"name": "数组练习", "due_date": "2099-08-06"},
        headers=client.csrf_headers,
    )
    with dashboard_app.app.test_client() as anonymous:
        renamed = anonymous.get(path).get_data(as_text=True)
    assert renamed.count(task_uid) == 1
    assert renamed.count(due_uid) == 1
    assert "SUMMARY:数组练习 · Python 数据处理" in renamed
    assert "DTSTART;VALUE=DATE:20990806" in renamed
    assert "NumPy 练习" not in renamed

    client.post(
        f"/api/projects/{project['id']}/archive",
        headers=client.csrf_headers,
    )
    with dashboard_app.app.test_client() as anonymous:
        archived = anonymous.get(path).get_data(as_text=True)
    assert task_uid not in archived
    assert due_uid not in archived

    client.post(
        f"/api/projects/{project['id']}/reopen",
        headers=client.csrf_headers,
    )
    with dashboard_app.app.test_client() as anonymous:
        reopened = anonymous.get(path).get_data(as_text=True)
    assert reopened.count(task_uid) == 1
    assert reopened.count(due_uid) == 1


def test_calendar_subscription_is_unavailable_until_https_activation(calendar_client, monkeypatch):
    client, _ = calendar_client
    monkeypatch.setattr(dashboard_app.settings, "APPLE_CALENDAR_ENABLED", False)

    created = client.post("/api/apple-calendar/subscription", headers=client.csrf_headers)

    assert created.status_code == 404
    with dashboard_app.app.test_client() as anonymous_client:
        assert anonymous_client.get("/calendar/not-a-token.ics").status_code == 404
