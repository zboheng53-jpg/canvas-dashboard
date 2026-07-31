import json
import threading

import app as dashboard_app
import project_store
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


def _create_project(client, headers, name="Python 学习", **extra):
    response = _post(client, headers, "/api/projects", {"name": name, **extra})
    assert response.status_code == 200
    return response.get_json()["project"]


def _create_task(client, headers, project_id, name="完成 NumPy 练习", **extra):
    response = _post(
        client,
        headers,
        f"/api/projects/{project_id}/tasks",
        {"name": name, **extra},
    )
    assert response.status_code == 200
    return response.get_json()["task"]


def test_create_and_edit_project_without_automatic_main(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _create_project(
        client,
        headers,
        objective="能够完成数学建模数据处理",
        due_date="2026-09-01",
    )

    payload = client.get("/api/projects").get_json()
    assert payload["main_project_id"] is None
    assert project["status"] == "active"
    assert project["objective"] == "能够完成数学建模数据处理"
    assert project["completed_count"] == 0
    assert project["pending_count"] == 0

    updated = client.put(
        f"/api/projects/{project['id']}",
        json={"name": "Python 数据处理", "due_date": None},
        headers=headers,
    ).get_json()["project"]
    assert updated["name"] == "Python 数据处理"
    assert updated["due_date"] is None


def test_main_project_is_unique_and_cleared_on_complete_or_archive(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    first = _create_project(client, headers, "项目一")
    second = _create_project(client, headers, "项目二")

    _post(client, headers, f"/api/projects/{first['id']}/set-main")
    result = _post(client, headers, f"/api/projects/{second['id']}/set-main").get_json()
    assert result["main_project_id"] == second["id"]

    completed = _post(client, headers, f"/api/projects/{second['id']}/complete").get_json()
    assert completed["project"]["status"] == "completed"
    assert completed["main_project_id"] is None

    _post(client, headers, f"/api/projects/{first['id']}/set-main")
    archived = _post(client, headers, f"/api/projects/{first['id']}/archive").get_json()
    assert archived["project"]["status"] == "archived"
    assert archived["main_project_id"] is None


def test_groups_create_rename_reorder_and_nonempty_delete_moves_tasks(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _create_project(client, headers)
    first = _post(
        client,
        headers,
        f"/api/projects/{project['id']}/groups",
        {"name": "基础"},
    ).get_json()["group"]
    second = _post(
        client,
        headers,
        f"/api/projects/{project['id']}/groups",
        {"name": "数据处理"},
    ).get_json()["group"]

    renamed = client.put(
        f"/api/projects/{project['id']}/groups/{first['id']}",
        json={"name": "语言基础"},
        headers=headers,
    ).get_json()["group"]
    assert renamed["name"] == "语言基础"

    reordered = _post(
        client,
        headers,
        f"/api/projects/{project['id']}/groups/reorder",
        {"group_ids": [second["id"], first["id"]]},
    ).get_json()["groups"]
    assert [group["id"] for group in reordered] == [second["id"], first["id"]]

    task = _create_task(client, headers, project["id"], group_id=second["id"])
    deleted = client.delete(
        f"/api/projects/{project['id']}/groups/{second['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    refreshed = client.get("/api/projects").get_json()["projects"][0]
    assert all(group["id"] != second["id"] for group in refreshed["groups"])
    assert next(item for item in refreshed["tasks"] if item["id"] == task["id"])["group_id"] is None


def test_task_crud_next_action_completion_and_stats(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _create_project(client, headers)
    first = _create_task(
        client,
        headers,
        project["id"],
        "阅读 NumPy 文档",
        due_date="2026-07-30",
        is_next_action=True,
    )
    second = _create_task(client, headers, project["id"], "完成练习")

    updated = client.put(
        f"/api/projects/{project['id']}/tasks/{second['id']}",
        json={
            "name": "完成数组练习",
            "due_date": "2026-08-01",
            "is_next_action": True,
        },
        headers=headers,
    ).get_json()["task"]
    assert updated["is_next_action"] is True

    refreshed = client.get("/api/projects").get_json()["projects"][0]
    assert next(task for task in refreshed["tasks"] if task["id"] == first["id"])["is_next_action"] is False
    assert refreshed["pending_count"] == 2

    done = client.put(
        f"/api/projects/{project['id']}/tasks/{second['id']}",
        json={"done": True},
        headers=headers,
    ).get_json()["task"]
    assert done["done"] is True
    assert done["is_next_action"] is False
    assert done["completed_at"]

    restored = client.put(
        f"/api/projects/{project['id']}/tasks/{second['id']}",
        json={"done": False},
        headers=headers,
    ).get_json()["task"]
    assert restored["completed_at"] is None

    deleted = client.delete(
        f"/api/projects/{project['id']}/tasks/{first['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    refreshed = client.get("/api/projects").get_json()["projects"][0]
    assert refreshed["pending_count"] == 1
    assert [task["id"] for task in refreshed["tasks"]] == [second["id"]]


def test_task_move_and_reorder_validates_complete_order(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _create_project(client, headers)
    group = _post(
        client,
        headers,
        f"/api/projects/{project['id']}/groups",
        {"name": "练习"},
    ).get_json()["group"]
    first = _create_task(client, headers, project["id"], "任务一")
    second = _create_task(client, headers, project["id"], "任务二")

    moved = _post(
        client,
        headers,
        f"/api/projects/{project['id']}/tasks/reorder",
        {
            "tasks": [
                {"id": second["id"], "group_id": group["id"]},
                {"id": first["id"], "group_id": None},
            ]
        },
    ).get_json()["tasks"]
    assert [(task["id"], task["group_id"], task["sort_order"]) for task in moved] == [
        (second["id"], group["id"], 0),
        (first["id"], None, 0),
    ]

    invalid = _post(
        client,
        headers,
        f"/api/projects/{project['id']}/tasks/reorder",
        {"tasks": [{"id": first["id"], "group_id": None}]},
    )
    assert invalid.status_code == 400


def test_complete_archive_and_reopen_preserve_unfinished_tasks(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    project = _create_project(client, headers, due_date="2026-01-01")
    task = _create_task(client, headers, project["id"], due_date="2026-01-02")

    completed = _post(client, headers, f"/api/projects/{project['id']}/complete").get_json()["project"]
    assert completed["status"] == "completed"
    assert completed["completed_at"]
    assert next(item for item in completed["tasks"] if item["id"] == task["id"])["done"] is False

    reopened = _post(client, headers, f"/api/projects/{project['id']}/reopen").get_json()["project"]
    assert reopened["status"] == "active"
    assert reopened["completed_at"] is None
    assert reopened["archived_at"] is None

    archived = _post(client, headers, f"/api/projects/{project['id']}/archive").get_json()["project"]
    assert archived["status"] == "archived"
    assert archived["archived_at"]


def test_project_overview_main_only_and_upcoming_task_order(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    main = _create_project(client, headers, "主项目", objective="一句话目标", due_date="2026-07-30")
    _create_project(client, headers, "另一个项目")
    next_task = _create_task(client, headers, main["id"], "下一步", is_next_action=True)
    overdue = _create_task(client, headers, main["id"], "逾期", due_date="2026-01-01")
    dated = _create_task(client, headers, main["id"], "有日期", due_date="2026-08-01")
    _create_task(client, headers, main["id"], "无日期")
    _post(client, headers, f"/api/projects/{main['id']}/set-main")

    overview = client.get("/api/projects/overview").get_json()
    assert overview["main_project"]["id"] == main["id"]
    assert overview["main_project"]["next_action"]["id"] == next_task["id"]
    assert [task["id"] for task in overview["main_project"]["upcoming_tasks"]] == [
        overdue["id"],
        dated["id"],
    ]
    assert overview["main_project"]["hidden_task_count"] == 1
    assert overview["active_project_count"] == 2


def test_project_and_group_order_and_last_viewed_are_persisted(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    first = _create_project(client, headers, "一")
    second = _create_project(client, headers, "二")
    _post(
        client,
        headers,
        "/api/projects/reorder",
        {"project_ids": [second["id"], first["id"]]},
    )
    _post(client, headers, f"/api/projects/{first['id']}/viewed")

    payload = client.get("/api/projects").get_json()
    assert [project["id"] for project in payload["projects"]] == [second["id"], first["id"]]
    assert payload["last_viewed_project_id"] == first["id"]


def test_validation_auth_csrf_and_user_isolation(tmp_path, monkeypatch):
    alice, headers = _client(tmp_path, monkeypatch, "alice")
    assert _post(alice, headers, "/api/projects", {"name": ""}).status_code == 400
    assert _post(alice, headers, "/api/projects", {"name": "x", "due_date": "bad"}).status_code == 400
    project = _create_project(alice, headers, "Alice")
    assert _post(
        alice,
        headers,
        f"/api/projects/{project['id']}/tasks",
        {"name": "x", "due_date": "2026-99-99"},
    ).status_code == 400
    assert alice.post("/api/projects", json={"name": "blocked"}).status_code == 403

    bob, _ = _client(tmp_path, monkeypatch, "bob")
    assert bob.get("/api/projects").get_json()["projects"] == []
    with dashboard_app.app.test_client() as anonymous:
        assert anonymous.get("/api/projects").status_code == 401


def test_project_storage_concurrent_task_updates_do_not_lose_data(tmp_path, monkeypatch):
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    project = project_store.create_project("alice", {"name": "并发项目"})
    threads = [
        threading.Thread(
            target=project_store.create_task,
            args=("alice", project["id"], {"name": f"任务{i}"}),
        )
        for i in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(project_store.load_projects("alice")[0]["tasks"]) == 12


def test_legacy_array_is_upgraded_without_discarding_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    path = user_paths.user_dir("alice") / "projects.json"
    path.write_text(
        json.dumps([{"id": 7, "name": "旧项目", "status": "active", "goals": [{"id": 3, "text": "旧目标"}]}]),
        encoding="utf-8",
    )
    projects = project_store.load_projects("alice")
    assert projects[0]["id"] == 7
    assert projects[0]["name"] == "旧项目"
    assert projects[0]["tasks"][0]["name"] == "旧目标"


def test_project_json_corruption_fails_closed(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    path = user_paths.user_dir("alice") / "projects.json"
    path.write_text("{bad", encoding="utf-8")
    assert client.get("/api/projects").status_code == 503
    assert path.read_text(encoding="utf-8") == "{bad"
    assert list(path.parent.glob("projects.json.corrupt-*"))
