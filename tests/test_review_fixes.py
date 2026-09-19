import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import agent_auth
import agent_mcp
import app as dashboard
import auth
import canvas_auth
import platform_sync
import project_store
import schedule_store
import storage
import user_paths

CST = timezone(timedelta(hours=8))


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir(parents=True, exist_ok=True)
    for module in [dashboard, agent_auth, auth, canvas_auth, platform_sync, project_store, schedule_store, storage, user_paths]:
        for k, v in list(vars(module).items()):
            if isinstance(v, Path) and ("data" in str(v).lower() or k.endswith("_DIR") or k.endswith("_FILE") or k == "DATA_DIR"):
                monkeypatch.setattr(module, k, base / v.name if v.name != "data" and k != "DATA_DIR" else base)
    monkeypatch.setattr(user_paths, "DATA_DIR", base)
    dashboard.app.config.update(TESTING=True)
    auth.register("alice", "ReviewPass123!")
    auth.register("bob", "ReviewPass123!")
    alice_token = agent_auth.create_token("alice")
    bob_token = agent_auth.create_token("bob")
    client = dashboard.app.test_client()
    return {
        "base": base,
        "client": client,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "alice_headers": {"Authorization": f"Bearer {alice_token}"},
        "bob_headers": {"Authorization": f"Bearer {bob_token}"},
    }


def test_atomic_write_preserves_file_on_write_interruption(tmp_path):
    target = tmp_path / "data.json"
    storage.write_json_file(target, {"original": "intact"})
    original_content = target.read_text(encoding="utf-8")

    real_fdopen = os.fdopen
    def fail_mid_write(*args, **kwargs):
        f = real_fdopen(*args, **kwargs)
        f.write(b'{"corrupt":')
        raise OSError("Simulated write interruption")

    with patch("os.fdopen", fail_mid_write):
        with pytest.raises(OSError):
            storage.write_json_file(target, {"new": "broken"})

    # Original file must be preserved
    assert target.read_text(encoding="utf-8") == original_content


def test_custom_todo_monotonic_id_never_reused(test_env):
    client = test_env["client"]
    headers = test_env["alice_headers"]

    # Create task 1
    r1 = client.post("/api/agent/v1/todos", headers=headers, json={"text": "Task 1"}).get_json()
    t1_id = r1["todo"]["id"]

    # Delete task 1
    with client.session_transaction() as sess:
        sess.update(username="alice", account_id=auth.account_metadata("alice")["account_id"], session_version=1)
    client.delete(f"/api/custom/todos/{t1_id}")

    # Create task 2
    r2 = client.post("/api/agent/v1/todos", headers=headers, json={"text": "Task 2"}).get_json()
    t2_id = r2["todo"]["id"]

    # ID must not be reused
    assert t2_id > t1_id


def test_custom_todo_idempotency_key_prevents_duplicate(test_env):
    client = test_env["client"]
    headers = {**test_env["alice_headers"], "Idempotency-Key": "unique-op-key-1"}

    # First request
    r1 = client.post("/api/agent/v1/todos", headers=headers, json={"text": "Idempotent Task"})
    assert r1.status_code == 201
    created_id = r1.get_json()["todo"]["id"]

    # Retry identical request
    r2 = client.post("/api/agent/v1/todos", headers=headers, json={"text": "Idempotent Task"})
    assert r2.status_code == 201
    assert r2.get_json()["todo"]["id"] == created_id

    # Verify only one item was persisted
    todos = dashboard._load_todos("alice")
    matching = [t for t in todos if t["text"] == "Idempotent Task"]
    assert len(matching) == 1

    # Retry with different payload should conflict (409)
    r3 = client.post("/api/agent/v1/todos", headers=headers, json={"text": "Different Content"})
    assert r3.status_code == 409


def test_proxy_fix_and_external_url_generation(test_env):
    client = test_env["client"]
    with client.session_transaction(base_url="http://canvas-dashboard.xyz") as session:
        session.update(username="alice", account_id=auth.account_metadata("alice")["account_id"], session_version=1)

    proxy_headers = {"Host": "canvas-dashboard.xyz", "X-Forwarded-Proto": "https"}
    res = client.get("/api/agent/export/mcp-bundle.zip", base_url="http://canvas-dashboard.xyz", headers=proxy_headers)
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.data)) as zf:
        claude = json.loads(zf.read("claude_desktop_config.json"))["mcpServers"]["canvas-dashboard"]
        cursor = json.loads(zf.read("cursor_mcp.json"))["mcpServers"]["canvas-dashboard"]

    assert claude["env"]["CANVAS_DASHBOARD_URL"] == "https://canvas-dashboard.xyz"
    assert cursor["env"]["CANVAS_DASHBOARD_URL"] == "https://canvas-dashboard.xyz"
    assert claude["command"] == "python"
    assert claude["args"] == ["canvas_mcp.py"]
    assert cursor["command"] == "python"
    assert cursor["args"] == ["canvas_mcp.py"]


def test_agent_client_rejects_non_loopback_http():
    # Loopback is allowed for local development
    local_client = agent_mcp.CanvasDashboardClient("http://127.0.0.1:5000", "cda_dummy")
    assert local_client.base_url == "http://127.0.0.1:5000"

    # Remote HTTP is rejected
    remote_client = agent_mcp.CanvasDashboardClient("http://canvas-dashboard.xyz", "cda_dummy")
    with pytest.raises(ValueError, match="安全限制：非本地回环地址"):
        remote_client.request("/api/agent/v1/ping")


def test_agent_complete_project_due_item(test_env):
    client = test_env["client"]
    headers = test_env["alice_headers"]

    proj = project_store.create_project("alice", {"name": "Semester Project", "due_date": "2026-09-30"})
    proj_id = proj["id"]

    # Complete due item
    res = client.post(f"/api/agent/v1/todos/due-{proj_id}/complete", headers=headers, json={"source": "project"})
    assert res.status_code == 200
    assert res.get_json()["completed"] is True

    # Check project status is completed
    state = project_store.load_state("alice")
    found = next((p for p in state["projects"] if p["id"] == proj_id), None)
    assert found is not None
    assert found["status"] == "completed"


def test_agent_complete_nonexistent_platform_todo_returns_404(test_env):
    client = test_env["client"]
    headers = test_env["alice_headers"]

    for source in ["canvas", "haoke", "zhixuemeng", "zhihuishu"]:
        res = client.post(f"/api/agent/v1/todos/nonexistent-99999/complete", headers=headers, json={"source": source})
        assert res.status_code == 404
        assert res.get_json()["code"] == "todo_not_found"


def test_agent_auth_deleted_account_cannot_authenticate(test_env):
    client = test_env["client"]
    headers = test_env["alice_headers"]

    # Ping passes initially
    assert client.get("/api/agent/v1/ping", headers=headers).status_code == 200

    # Delete alice from users.json (simulating orphaned files on abnormal deletion)
    storage.locked_json_update(auth.USERS_FILE, {}, lambda users: {k: v for k, v in users.items() if k != "alice"})

    # Ping must be rejected with 401
    res = client.get("/api/agent/v1/ping", headers=headers)
    assert res.status_code == 401


def test_agent_auth_single_user_corruption_does_not_break_others(test_env):
    client = test_env["client"]
    bob_headers = test_env["bob_headers"]
    base = test_env["base"]

    # Corrupt Alice's token file
    alice_token_file = base / "users" / "alice" / "agent_token.json"
    alice_token_file.write_text('{"bad": json', encoding="utf-8")

    # Bob's request must still succeed with 200
    res = client.get("/api/agent/v1/ping", headers=bob_headers)
    assert res.status_code == 200


def test_agent_todos_contains_subtasks_and_sync_status(test_env):
    client = test_env["client"]
    headers = test_env["alice_headers"]

    # Create parent task
    t = client.post("/api/agent/v1/todos", headers=headers, json={"text": "Parent Task"}).get_json()["todo"]
    storage.locked_json_update(user_paths.user_dir("alice") / "custom_todos.json", [], lambda ts: [
        dict(item, subtasks=[{"id": 101, "text": "Subtask 101", "done": False}]) if item["id"] == t["id"] else item for item in ts
    ])

    res = client.get("/api/agent/v1/todos", headers=headers).get_json()
    assert res["ok"] is True
    assert "sync_status" in res
    titles = [item["title"] for item in res["todos"]]
    assert "Parent Task" in titles
    assert "Subtask 101" in titles

    # Complete the subtask via Agent API
    comp_res = client.post(f"/api/agent/v1/todos/{t['id']}:101/complete", headers=headers)
    assert comp_res.status_code == 200

    # Verify subtask is done
    updated_todos = dashboard._load_todos("alice")
    parent = next(item for item in updated_todos if item["id"] == t["id"])
    assert parent["subtasks"][0]["done"] is True


def test_canvas_auth_retains_overdue_within_30_days():
    # Sample iCal with an assignment due 5 days ago
    past_date = (datetime.now(CST) - timedelta(days=5)).strftime("%Y%m%dT%H%M%S")
    ical_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test Calendar//EN
BEGIN:VEVENT
UID:event-12345
DTSTART:{past_date}
DTEND:{past_date}
SUMMARY:Overdue HW within 30 days
DESCRIPTION:课程: 操作系统
URL:https://canvas.tongji.edu.cn/assignments/12345
END:VEVENT
END:VCALENDAR
"""
    items = canvas_auth._parse_ical(ical_content)
    assert len(items) == 1
    assert items[0]["title"] == "Overdue HW within 30 days"


def test_register_per_ip_rate_limit(test_env):
    client = test_env["client"]
    dashboard._rate_limit_buckets.clear()

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "csrf-test-token"

    statuses = []
    for i in range(7):
        res = client.post(
            "/api/auth/register",
            headers={"X-CSRF-Token": "csrf-test-token", "X-Real-IP": "198.51.100.22"},
            json={"username": f"user_batch_{i}", "password": "ReviewPass123!"},
        )
        statuses.append(res.status_code)

    # First 5 attempts succeed, 6th and 7th get 429
    assert statuses[:5] == [200, 200, 200, 200, 200]
    assert statuses[5:] == [429, 429]


def test_mcp_stdio_robustness():
    # Unknown tool call returns isError: True
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nonexistent_tool", "arguments": {}}}
    proc = subprocess.run(
        [sys.executable, str(Path(agent_mcp.__file__).resolve())],
        input=(json.dumps(payload) + "\n").encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    res = json.loads(proc.stdout.decode("utf-8"))
    assert res["result"]["isError"] is True

    # Malformed envelope [] does not crash the server
    proc2 = subprocess.run(
        [sys.executable, str(Path(agent_mcp.__file__).resolve())],
        input=b'[]\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n',
        capture_output=True,
        timeout=10,
    )
    assert proc2.returncode == 0
    res2 = json.loads(proc2.stdout.decode("utf-8"))
    assert res2["id"] == 2
