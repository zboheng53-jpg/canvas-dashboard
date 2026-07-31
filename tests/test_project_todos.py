import app as dashboard_app
import user_paths


def _client(tmp_path, monkeypatch, username="alice"):
    def resolve(name):
        path = tmp_path / "users" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", resolve)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session:
        session["username"] = username
        session["_csrf_token"] = "csrf"
    return client, {"X-CSRF-Token": "csrf"}


def _post(client, headers, path, payload=None):
    return client.post(path, json=payload, headers=headers)


def _project(client, headers, **payload):
    return _post(client, headers, "/api/projects", {"name": "Python 学习", **payload}).get_json()["project"]


def _task(client, headers, project_id, name, **payload):
    return _post(
        client,
        headers,
        f"/api/projects/{project_id}/tasks",
        {"name": name, **payload},
    ).get_json()["task"]


def test_only_active_undone_dated_project_tasks_and_project_due_are_listed(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _project(client, headers, due_date="2026-09-01")
    dated = _task(client, headers, project["id"], "有日期", due_date="2026-07-30")
    undated = _task(client, headers, project["id"], "无日期")
    done = _task(client, headers, project["id"], "已完成", due_date="2026-08-02")
    client.put(
        f"/api/projects/{project['id']}/tasks/{done['id']}",
        json={"done": True},
        headers=headers,
    )

    payload = client.get("/api/projects/todos").get_json()
    assert payload["count"] == 2
    assert {(item["kind"], item["title"]) for item in payload["items"]} == {
        ("project_task", dated["name"]),
        ("project_due", "完成项目：Python 学习"),
    }
    assert all(item["source"] == "Project" for item in payload["items"])
    assert undated["name"] not in {item["title"] for item in payload["items"]}


def test_completed_archived_and_reopened_projects_update_todo_membership(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _project(client, headers, due_date="2026-09-01")
    _task(client, headers, project["id"], "任务", due_date="2026-07-30")
    assert client.get("/api/projects/todos").get_json()["count"] == 2

    _post(client, headers, f"/api/projects/{project['id']}/complete")
    assert client.get("/api/projects/todos").get_json()["items"] == []

    _post(client, headers, f"/api/projects/{project['id']}/reopen")
    assert client.get("/api/projects/todos").get_json()["count"] == 2

    _post(client, headers, f"/api/projects/{project['id']}/archive")
    assert client.get("/api/projects/todos").get_json()["items"] == []


def test_todo_actions_write_back_to_single_project_source(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _project(client, headers, due_date="2026-09-01")
    task = _task(client, headers, project["id"], "任务", due_date="2026-07-30")

    client.put(
        f"/api/projects/{project['id']}/tasks/{task['id']}",
        json={"highlighted": True, "due_date": "2026-08-05"},
        headers=headers,
    )
    items = client.get("/api/projects/todos").get_json()["items"]
    task_item = next(item for item in items if item["kind"] == "project_task")
    assert task_item["flagged"] is True
    assert task_item["due_date"] == "2026-08-05"

    client.put(
        f"/api/projects/{project['id']}/tasks/{task['id']}",
        json={"done": True},
        headers=headers,
    )
    items = client.get("/api/projects/todos").get_json()["items"]
    assert all(item["kind"] != "project_task" for item in items)

    client.put(
        f"/api/projects/{project['id']}",
        json={"due_highlighted": True, "due_date": "2026-09-03"},
        headers=headers,
    )
    due = client.get("/api/projects/todos").get_json()["items"][0]
    assert due["kind"] == "project_due"
    assert due["flagged"] is True
    assert due["due_date"] == "2026-09-03"


def test_project_todos_are_user_isolated(tmp_path, monkeypatch):
    alice, headers = _client(tmp_path, monkeypatch, "alice")
    project = _project(alice, headers, due_date="2026-09-01")
    _task(alice, headers, project["id"], "Alice 任务", due_date="2026-07-30")

    bob, _ = _client(tmp_path, monkeypatch, "bob")
    assert bob.get("/api/projects/todos").get_json()["items"] == []
