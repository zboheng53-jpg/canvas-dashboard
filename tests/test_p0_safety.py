import json
import logging
from logging.handlers import RotatingFileHandler

import pytest

import app as dashboard_app


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "custom_todos.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


def test_custom_todo_post_rejects_non_json_request(client_with_user):
    resp = client_with_user.post(
        "/api/custom/todos",
        data="not-json",
        content_type="text/plain",
        headers=client_with_user.csrf_headers,
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_custom_todo_put_rejects_json_null(client_with_user):
    resp = client_with_user.put(
        "/api/custom/todos/1",
        data="null",
        content_type="application/json",
        headers=client_with_user.csrf_headers,
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_ocr_api_routes_are_not_registered():
    ocr_rules = [rule.rule for rule in dashboard_app.app.url_map.iter_rules() if rule.rule.startswith("/api/ocr/")]

    assert ocr_rules == []


def test_storage_locked_json_update_serializes_updates(tmp_path):
    import storage

    path = tmp_path / "todos.json"
    storage.write_json_file(path, [])

    def add_one(items):
        items.append({"id": len(items) + 1})
        return items

    storage.locked_json_update(path, [], add_one)
    storage.locked_json_update(path, [], add_one)

    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": 1}, {"id": 2}]


def test_serve_uses_rotating_file_handler(tmp_path):
    import serve

    handlers = serve._create_log_handlers(tmp_path / "server.log")

    file_handlers = [h for h in handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes > 0
    assert file_handlers[0].backupCount > 0
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)
