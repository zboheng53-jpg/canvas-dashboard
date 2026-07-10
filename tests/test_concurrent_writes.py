import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

import app as dashboard_app
from platform_state import PlatformStateStore


def _csrf_headers(client, token="csrf-test-token"):
    with client.session_transaction() as sess:
        sess["username"] = "alice"
        sess["_csrf_token"] = token
    return {"X-CSRF-Token": token}


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "custom_todos.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    dashboard_app.app.config.update(TESTING=True)
    return user_dir


def test_custom_todo_consecutive_puts_preserve_unrelated_fields(isolated_app):
    todo_file = isolated_app / "custom_todos.json"
    todo_file.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "text": "Original",
                    "done": False,
                    "created_at": "2026-07-09T08:00:00+08:00",
                    "due_date": "2099-07-10",
                    "highlighted": False,
                    "labels": ["old"],
                    "subtasks": [{"id": 1, "text": "Subtask", "done": False}],
                }
            ]
        ),
        encoding="utf-8",
    )

    with dashboard_app.app.test_client() as client:
        headers = _csrf_headers(client)
        labels_resp = client.put("/api/custom/todos/1", json={"labels": ["lab", "urgent"]}, headers=headers)
        text_resp = client.put("/api/custom/todos/1", json={"text": "Renamed"}, headers=headers)

    stored = json.loads(todo_file.read_text(encoding="utf-8"))[0]
    assert labels_resp.status_code == 200
    assert text_resp.status_code == 200
    assert stored["text"] == "Renamed"
    assert stored["labels"] == ["lab", "urgent"]
    assert stored["due_date"] == "2099-07-10"
    assert stored["subtasks"] == [{"id": 1, "text": "Subtask", "done": False}]


def test_custom_todo_concurrent_posts_do_not_drop_items(isolated_app):
    todo_file = isolated_app / "custom_todos.json"

    def post_todo(i):
        with dashboard_app.app.test_client() as client:
            headers = _csrf_headers(client, f"csrf-{i}")
            resp = client.post(
                "/api/custom/todos",
                json={"text": f"Task {i}", "labels": [f"tag{i}"]},
                headers=headers,
            )
            assert resp.status_code == 200

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(post_todo, range(20)))

    stored = json.loads(todo_file.read_text(encoding="utf-8"))
    assert len(stored) == 20
    assert {item["text"] for item in stored} == {f"Task {i}" for i in range(20)}
    assert sorted(item["id"] for item in stored) == list(range(1, 21))
    assert all("labels" in item and "subtasks" in item for item in stored)


def test_expired_custom_todo_cleanup_preserves_active_todos(isolated_app):
    todo_file = isolated_app / "custom_todos.json"
    todo_file.write_text(
        json.dumps(
            [
                {"id": 1, "text": "Expired", "done": True, "due_date": "2026-07-09"},
                {"id": 2, "text": "Keep", "done": False, "due_date": "2026-07-11"},
            ]
        ),
        encoding="utf-8",
    )

    todos = dashboard_app._remove_expired_completed_todos("alice", date(2026, 7, 10))

    assert [todo["id"] for todo in todos] == [2]
    assert [todo["id"] for todo in json.loads(todo_file.read_text(encoding="utf-8"))] == [2]


def test_platform_state_consecutive_updates_preserve_fields(tmp_path):
    store = PlatformStateStore(lambda username: tmp_path / username / "canvas_state.json", int)

    store.update("alice", "hide", 1)
    state = store.update("alice", "highlight", 2)

    assert state["hidden"] == [1]
    assert state["highlighted"] == [2]
    assert state["deleted"] == []


def test_platform_state_concurrent_updates_do_not_drop_fields(tmp_path):
    store = PlatformStateStore(lambda username: tmp_path / username / "canvas_state.json", int)

    def update(i):
        if i % 2 == 0:
            store.update("alice", "hide", i)
        else:
            store.update("alice", "highlight", i)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(update, range(40)))

    state = store.load("alice")
    assert sorted(state["hidden"]) == list(range(0, 40, 2))
    assert sorted(state["highlighted"]) == list(range(1, 40, 2))
    assert state["deleted"] == []
