import threading

import app as dashboard_app
import project_store
import user_paths


def _client(tmp_path, monkeypatch, username="alice"):
    def resolve(name):
        path = tmp_path / "users" / name; path.mkdir(parents=True, exist_ok=True); return path
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path); monkeypatch.setattr(dashboard_app, "user_dir", resolve)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session: session["username"] = username; session["_csrf_token"] = "csrf"
    return client, {"X-CSRF-Token": "csrf"}


def test_project_crud_goals_sort_archive_and_bounds(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    bad = client.post("/api/projects", json={"name":"x","progress":101}, headers=headers)
    assert bad.status_code == 400
    assert client.post("/api/projects", json={"name":"x","progress":-1}, headers=headers).status_code == 400
    project = client.post("/api/projects", json={"name":"毕业设计","progress":20,"due_date":"2026-08-01","next_action":"整理实验数据"}, headers=headers).get_json()["project"]
    first = client.post(f"/api/projects/{project['id']}/goals", json={"text":"完成模型"}, headers=headers).get_json()["goal"]
    second = client.post(f"/api/projects/{project['id']}/goals", json={"text":"写周报"}, headers=headers).get_json()["goal"]
    assert client.put(f"/api/projects/{project['id']}/goals/{first['id']}", json={"done":True}, headers=headers).get_json()["goal"]["done"]
    assert client.post(f"/api/projects/{project['id']}/goals/reorder", json={"goal_ids":[second['id'], first['id']]}, headers=headers).status_code == 200
    assert client.put(f"/api/projects/{project['id']}", json={"progress":100}, headers=headers).get_json()["project"]["progress"] == 100
    assert client.put(f"/api/projects/{project['id']}", json={"progress":80,"next_action":"提交初稿"}, headers=headers).get_json()["project"]["progress"] == 80
    assert client.post(f"/api/projects/{project['id']}/archive", headers=headers).get_json()["project"]["status"] == "archived"


def test_project_overview_returns_three_active_projects(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    projects = [
        client.post("/api/projects", json={"name": f"项目{i}"}, headers=headers).get_json()["project"]
        for i in range(1, 6)
    ]
    client.post(f"/api/projects/{projects[0]['id']}/archive", headers=headers)

    overview = client.get("/api/projects/overview").get_json()

    assert [project["name"] for project in overview["projects"]] == ["项目2", "项目3", "项目4"]
    assert overview["has_more"] is True
    assert all(project["status"] == "active" for project in overview["projects"])


def test_projects_are_isolated_and_mutations_need_auth_and_csrf(tmp_path, monkeypatch):
    alice, headers = _client(tmp_path, monkeypatch, "alice")
    alice.post("/api/projects", json={"name":"A"}, headers=headers)
    bob, _ = _client(tmp_path, monkeypatch, "bob")
    assert bob.get("/api/projects").get_json()["projects"] == []
    assert alice.post("/api/projects", json={"name":"blocked"}).status_code == 403
    with dashboard_app.app.test_client() as anonymous: assert anonymous.get("/api/projects").status_code == 401


def test_project_storage_handles_concurrent_goal_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    project = project_store.create_project("alice", {"name":"并发项目"})
    threads = [threading.Thread(target=project_store.create_goal, args=("alice", project["id"], f"目标{i}")) for i in range(8)]
    [thread.start() for thread in threads]; [thread.join() for thread in threads]
    assert len(project_store.load_projects("alice")[0]["goals"]) == 8


def test_project_json_corruption_fails_closed(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    path = user_paths.user_dir("alice") / "projects.json"; path.write_text("{bad", encoding="utf-8")
    assert client.get("/api/projects").status_code == 503
