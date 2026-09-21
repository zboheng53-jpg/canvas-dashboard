import io
import json
import zipfile
from datetime import datetime, timezone, timedelta
import pytest

import app as dashboard_app
import agent_auth
import agent_mcp
import schedule_store
import user_paths


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "custom_todos.json").write_text("[]", encoding="utf-8")

    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth, "user_dir", lambda username: user_dir)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})

    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


def test_agent_api_authentication(client_with_user):
    # Missing Authorization header
    resp = client_with_user.get("/api/agent/v1/ping")
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False

    # Invalid token
    resp = client_with_user.get("/api/agent/v1/ping", headers={"Authorization": "Bearer cda_invalidtoken12345678901234567890"})
    assert resp.status_code == 401

    # Create real token
    token = agent_auth.create_token("alice")
    resp = client_with_user.get("/api/agent/v1/ping", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["username"] == "alice"


def test_agent_token_web_endpoints(client_with_user):
    # GET initial status
    resp = client_with_user.get("/api/agent/token")
    assert resp.status_code == 200
    assert resp.get_json()["has_token"] is False

    # POST create token
    resp = client_with_user.post("/api/agent/token", headers=client_with_user.csrf_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    token = data["token"]
    assert token.startswith("cda_")

    # DELETE revoke token
    resp = client_with_user.delete("/api/agent/token", headers=client_with_user.csrf_headers)
    assert resp.status_code == 200
    assert resp.get_json()["revoked"] is True
    assert resp.get_json()["has_token"] is False


def test_agent_api_schedule_and_todos_lifecycle(client_with_user):
    token = agent_auth.create_token("alice")
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Query today schedule
    resp = client_with_user.get("/api/agent/v1/schedule/today", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert "timed" in resp.get_json()

    # Query timetable
    resp = client_with_user.get("/api/agent/v1/schedule/timetable", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Add custom todo
    resp = client_with_user.post(
        "/api/agent/v1/todos",
        headers=auth_headers,
        json={"text": "离散数学第三次作业", "due_date": "2026-09-10"},
    )
    assert resp.status_code == 201
    todo = resp.get_json()["todo"]
    assert todo["text"] == "离散数学第三次作业"
    todo_id = str(todo["id"])

    # Query todos list
    resp = client_with_user.get("/api/agent/v1/todos?source=all&status=pending", headers=auth_headers)
    assert resp.status_code == 200
    todos = resp.get_json()["todos"]
    assert any(t["id"] == todo_id for t in todos)

    # Complete todo
    resp = client_with_user.post(
        f"/api/agent/v1/todos/{todo_id}/complete",
        headers=auth_headers,
        json={"source": "custom"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["completed"] is True

    # Verify pending todos no longer includes it
    resp = client_with_user.get("/api/agent/v1/todos?source=all&status=pending", headers=auth_headers)
    todos = resp.get_json()["todos"]
    assert not any(t["id"] == todo_id for t in todos)


def test_agent_export_bundles(client_with_user):
    # MCP script download
    resp = client_with_user.get("/api/agent/export/mcp-script")
    assert resp.status_code == 200
    assert b"CanvasDashboardClient" in resp.data
    standalone_mcp = resp.data

    # MCP bundle zip download
    resp = client_with_user.get("/api/agent/export/mcp-bundle.zip")
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        namelist = zf.namelist()
        assert "canvas_mcp.py" in namelist
        assert "claude_desktop_config.json" in namelist
        assert "cursor_mcp.json" in namelist
        assert "README.md" in namelist
        assert zf.read("canvas_mcp.py") == standalone_mcp
        assert agent_mcp.WRITING_RULES in zf.read("README.md").decode("utf-8")

    # Skill bundle zip download
    resp = client_with_user.get("/api/agent/export/skill-bundle.zip")
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        namelist = zf.namelist()
        assert "SKILL.md" in namelist
        assert "canvas_api.py" in namelist
        assert "README.md" in namelist
        skill_text = zf.read("SKILL.md").decode("utf-8")
        assert agent_mcp.WRITING_RULES in skill_text
        assert client_with_user.get("/skill/SKILL.md").get_data(as_text=True).splitlines() == skill_text.splitlines()
        assert "planned_on" in skill_text
        assert "request_id" in skill_text
        assert "growth" in skill_text
        compile(zf.read("canvas_api.py"), "canvas_api.py", "exec")


def test_mcp_homework_roundtrip_in_ordinary_todos(client_with_user):
    """Verify the supported write/read path, not the model's choice of tool."""
    token = agent_auth.create_token("alice")
    headers = {"Authorization": f"Bearer {token}"}

    class LocalAgentClient:
        def request(self, endpoint, method="GET", data=None):
            response = client_with_user.open(endpoint, method=method, json=data, headers=headers)
            assert response.status_code in (200, 201), response.get_json()
            return response.get_json()

    api = LocalAgentClient()
    projects_before = api.request("/api/agent/v1/projects")
    homework = [
        ("完成工程材料海报", "2026-09-22", "提交课程海报"),
        ("提交机械制图作业", "2026-09-23", "每周三交；当前仅记录最近一次"),
        ("提交课程实验作业", "2026-09-24", "双周周四交，已确认最近一次为 9/24"),
    ]
    for index, (title, due, details) in enumerate(homework):
        payload = {"text": title, "due_date": due, "details": details,
                   "commitment": "obligation", "request_id": f"homework-{index}"}
        first = agent_mcp.handle_tool_call(api, "add_todo", payload)
        assert due in first
        assert agent_mcp.handle_tool_call(api, "add_todo", payload) == first

    todos = api.request("/api/agent/v1/todos?source=custom&status=pending")["todos"]
    assert len(todos) == 3
    assert {(t["title"], t["due_date"], t["details"]) for t in todos} == set(homework)
    assert all(t["source"] == "custom" and t["commitment"] == "obligation" for t in todos)
    visible = agent_mcp.handle_tool_call(api, "get_todos", {"source": "custom"})
    for title, due, _ in homework:
        assert title in visible and due in visible
    assert api.request("/api/agent/v1/projects") == projects_before
