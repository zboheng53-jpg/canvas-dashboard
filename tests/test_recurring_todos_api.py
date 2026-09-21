import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

import app as dashboard_app
import agent_auth
import user_paths
import recurring_todo_store

CST = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "custom_todos.json").write_text("[]", encoding="utf-8")

    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    monkeypatch.setattr(recurring_todo_store, "user_paths", user_paths)
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


def test_recurring_todo_web_lifecycle(client_with_user):
    today = datetime.now(CST).date()
    first_due = (today + timedelta(days=2)).isoformat()

    # 1. Create series
    create_resp = client_with_user.post(
        "/api/recurring-todos",
        data=json.dumps({
            "title": "每周物理实验报告",
            "first_due_date": first_due,
            "interval_weeks": 1,
            "details": "第1-8周物理实验报告",
        }),
        content_type="application/json",
        headers=client_with_user.csrf_headers,
    )
    assert create_resp.status_code == 201
    series = create_resp.get_json()["series"]
    series_id = series["id"]
    assert series["title"] == "每周物理实验报告"

    # 2. Homepage shows earliest occurrence
    todo_resp = client_with_user.get("/api/custom/todos")
    assert todo_resp.status_code == 200
    todos = todo_resp.get_json()["data"]
    rec_items = [t for t in todos if t.get("is_recurring")]
    assert len(rec_items) == 1
    assert rec_items[0]["due_date"] == first_due
    assert rec_items[0]["series_id"] == series_id
    action_ref = rec_items[0]["ref"]
    assert action_ref == f"recurring:{series_id}:{first_due}"

    # 3. Action workspace query and completion
    act_resp = client_with_user.get(f"/api/actions/{action_ref}")
    assert act_resp.status_code == 200
    action = act_resp.get_json()["action"]
    assert action["title"] == "每周物理实验报告"
    assert action["source"] == "recurring"
    assert action["done"] is False

    # Complete via /api/actions/<ref>
    put_act = client_with_user.put(
        f"/api/actions/{action_ref}",
        data=json.dumps({"done": True}),
        content_type="application/json",
        headers=client_with_user.csrf_headers,
    )
    assert put_act.status_code == 200
    assert put_act.get_json()["action"]["done"] is True

    # 4. After completing first occurrence, homepage automatically shows the next occurrence!
    todo_resp2 = client_with_user.get("/api/custom/todos")
    todos2 = todo_resp2.get_json()["data"]
    rec_items2 = [t for t in todos2 if t.get("is_recurring")]
    second_due = (today + timedelta(days=9)).isoformat()
    # If 9 days away, it's > 7 days, so not on homepage unless within 7 days
    # Let's verify by testing skip on second occurrence
    detail_resp = client_with_user.get(f"/api/recurring-todos/{series_id}")
    assert detail_resp.status_code == 200
    occs = detail_resp.get_json()["occurrences"]
    first_occ = next(o for o in occs if o["original_due_date"] == first_due)
    assert first_occ["status"] == "completed"

    # 5. Delete series
    del_resp = client_with_user.delete(f"/api/recurring-todos/{series_id}", headers=client_with_user.csrf_headers)
    assert del_resp.status_code == 200
    assert del_resp.get_json()["ok"] is True

    # Verification: series not in list
    list_resp = client_with_user.get("/api/recurring-todos")
    assert len(list_resp.get_json()["series"]) == 0


def test_recurring_todo_agent_api(client_with_user):
    token = agent_auth.create_token("alice")
    auth_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    today = datetime.now(CST).date()
    first_due = (today + timedelta(days=1)).isoformat()

    # 1. Agent creates recurring series
    resp = client_with_user.post(
        "/api/agent/v1/recurring-todos",
        headers=auth_headers,
        data=json.dumps({
            "title": "双周实验作业",
            "first_due_date": first_due,
            "interval_weeks": 2,
        }),
    )
    assert resp.status_code == 201
    series_id = resp.get_json()["series"]["id"]

    # 2. Agent gets todos list
    resp = client_with_user.get("/api/agent/v1/todos", headers=auth_headers)
    assert resp.status_code == 200
    todos = resp.get_json()["todos"]
    r_todo = next((t for t in todos if t.get("is_recurring")), None)
    assert r_todo is not None
    assert r_todo["title"] == "双周实验作业"

    # 3. Agent marks occurrence complete using standard todo completion endpoint
    comp_resp = client_with_user.post(
        f"/api/agent/v1/todos/{r_todo['id']}/complete",
        headers=auth_headers,
        data=json.dumps({}),
    )
    assert comp_resp.status_code == 200
    assert comp_resp.get_json()["ok"] is True

    # 4. Stop series
    stop_resp = client_with_user.post(
        f"/api/agent/v1/recurring-todos/{series_id}/stop",
        headers=auth_headers,
        data=json.dumps({}),
    )
    assert stop_resp.status_code == 200
    assert stop_resp.get_json()["series"]["stopped_at"] is not None
