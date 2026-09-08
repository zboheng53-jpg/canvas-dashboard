import app as dashboard_app
import project_store
import user_paths


def _client(tmp_path, monkeypatch, username="testuser"):
    def resolve(name):
        path = tmp_path / "users" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", resolve)
    dashboard_app.app.config.update(TESTING=True)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session:
        session["username"] = username
        session["_csrf_token"] = "csrf"
    return client, {"X-CSRF-Token": "csrf"}


def test_todo_items_include_category_next_action_and_main_flag(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)

    res1 = client.post("/api/projects", json={"name": "竞赛 | TU主线与技术积累", "due_date": "2026-10-01"}, headers=headers)
    p1 = res1.get_json()["project"]
    client.post(f"/api/projects/{p1['id']}/set-main", headers=headers)

    client.post(
        f"/api/projects/{p1['id']}/tasks",
        json={"name": "数模：确认分工与最小交付", "due_date": "2026-09-14", "is_next_action": True},
        headers=headers,
    )
    client.post(
        f"/api/projects/{p1['id']}/tasks",
        json={"name": "两周全局复盘", "due_date": "2026-09-27"},
        headers=headers,
    )

    res2 = client.post("/api/projects", json={"name": "英语 | 六级600+，雅思", "due_date": "2026-12-15"}, headers=headers)
    p2 = res2.get_json()["project"]
    client.post(
        f"/api/projects/{p2['id']}/tasks",
        json={"name": "完成一次完整六级诊断并记录分项错因", "due_date": "2026-09-19"},
        headers=headers,
    )

    todos_res = client.get("/api/projects/todos")
    assert todos_res.status_code == 200
    todos_data = todos_res.get_json()
    items = todos_data["items"]

    categories = {item["project_category"] for item in items}
    assert "竞赛" in categories
    assert "英语" in categories

    next_action_item = next(it for it in items if it["title"] == "数模：确认分工与最小交付")
    assert next_action_item["is_next_action"] is True
    assert next_action_item["is_main"] is True
    assert next_action_item["project_category"] == "竞赛"

    english_item = next(it for it in items if it["title"] == "完成一次完整六级诊断并记录分项错因")
    assert english_item["is_next_action"] is False
    assert english_item["is_main"] is False
    assert english_item["project_category"] == "英语"


def test_overview_includes_active_projects_and_preview_tasks(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)

    res1 = client.post("/api/projects", json={"name": "健身 | 稳定训练与引体进步"}, headers=headers)
    p1 = res1.get_json()["project"]
    client.post(f"/api/projects/{p1['id']}/set-main", headers=headers)

    res2 = client.post("/api/projects", json={"name": "竞赛 | TU主线与技术积累"}, headers=headers)
    p2 = res2.get_json()["project"]

    overview_res = client.get("/api/projects/overview")
    assert overview_res.status_code == 200
    data = overview_res.get_json()

    assert data["main_project"]["id"] == p1["id"]
    assert len(data["active_projects"]) == 2
    p1_active = next(p for p in data["active_projects"] if p["id"] == p1["id"])
    assert p1_active["is_main"] is True
    assert p1_active["project_category"] == "健身"

    p2_active = next(p for p in data["active_projects"] if p["id"] == p2["id"])
    assert p2_active["is_main"] is False
    assert p2_active["project_category"] == "竞赛"
