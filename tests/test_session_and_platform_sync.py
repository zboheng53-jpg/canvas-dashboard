import json
from datetime import datetime, timedelta

import app as dashboard_app
import auth
import platform_sync
import user_paths


def _configure_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(platform_sync, "user_dir", user_paths.user_dir)
    dashboard_app.app.config.update(TESTING=True)


def _csrf(client, token="csrf"):
    with client.session_transaction() as current:
        current["_csrf_token"] = token
    return {"X-CSRF-Token": token}


def _register(client, username="alice", password="strong-password"):
    response = client.post("/api/auth/register", json={"username": username, "password": password}, headers=_csrf(client))
    assert response.status_code == 200
    return password


def test_activity_endpoint_is_csrf_protected_and_throttled(tmp_path, monkeypatch):
    _configure_roots(tmp_path, monkeypatch)
    with dashboard_app.app.test_client() as client:
        _register(client)
        missing_csrf = client.post("/api/session/activity")
        assert missing_csrf.status_code == 403
        first = client.post("/api/session/activity", headers=_csrf(client))
        second = client.post("/api/session/activity", headers=_csrf(client))
        assert first.get_json()["refreshed"] is False  # login just refreshed it
        assert second.get_json()["refreshed"] is False
        assert client.get("/api/clock").headers.get("Set-Cookie") is None


def test_revoke_other_sessions_keeps_current_client_and_invalidates_other(tmp_path, monkeypatch):
    _configure_roots(tmp_path, monkeypatch)
    first = dashboard_app.app.test_client()
    second = dashboard_app.app.test_client()
    password = _register(first)
    login = second.post("/api/auth/login", json={"username": "alice", "password": password}, headers=_csrf(second, "second"))
    assert login.status_code == 200
    response = first.post("/api/account/sessions/revoke-others", json={"password": password}, headers=_csrf(first))
    assert response.status_code == 200
    assert first.get("/api/clock").status_code == 200
    assert second.get("/api/clock").status_code == 401


def test_expired_activity_is_rejected_without_waiting_for_browser_cookie(tmp_path, monkeypatch):
    _configure_roots(tmp_path, monkeypatch)
    with dashboard_app.app.test_client() as client:
        _register(client)
        with client.session_transaction() as current:
            current["last_active_at"] = (datetime.now(dashboard_app.CST) - timedelta(days=31)).isoformat()
        assert client.get("/api/clock").status_code == 401


def test_clear_canvas_data_only_removes_canvas_files_and_fails_closed(tmp_path, monkeypatch):
    _configure_roots(tmp_path, monkeypatch)
    directory = user_paths.user_dir("alice")
    directory.joinpath("config.json").write_text(json.dumps({"calendar_feed_url": "https://example.invalid/feed", "haoke_username": "h"}), encoding="utf-8")
    directory.joinpath("canvas_cache.json").write_text("[]", encoding="utf-8")
    directory.joinpath("canvas_state.json").write_text('{"hidden": [], "highlighted": [], "deleted": []}', encoding="utf-8")
    directory.joinpath("custom_todos.json").write_text("[]", encoding="utf-8")
    with dashboard_app.app.test_client() as client:
        _register(client)
        response = client.delete("/api/platform/canvas/data", headers=_csrf(client))
        assert response.status_code == 200
    assert not directory.joinpath("canvas_cache.json").exists()
    assert not directory.joinpath("canvas_state.json").exists()
    assert directory.joinpath("custom_todos.json").exists()
    assert json.loads(directory.joinpath("config.json").read_text(encoding="utf-8"))["haoke_username"] == "h"

    directory.joinpath("canvas_cache.json").write_text("{not-json", encoding="utf-8")
    with dashboard_app.app.test_client() as client:
        client.post("/api/auth/login", json={"username": "alice", "password": "strong-password"}, headers=_csrf(client, "again"))
        response = client.delete("/api/platform/canvas/data", headers=_csrf(client, "again"))
    assert response.status_code == 503
    assert directory.joinpath("canvas_cache.json").exists()


def test_disconnected_cache_is_not_calendar_eligible(tmp_path, monkeypatch):
    _configure_roots(tmp_path, monkeypatch)
    platform_sync.mark_disconnected("alice", "canvas", True)
    assert platform_sync.is_calendar_eligible("alice", "canvas") is False
    platform_sync.mark_connected("alice", "canvas")
    platform_sync.record_result("alice", "canvas", ok=True, has_cache=True)
    assert platform_sync.is_calendar_eligible("alice", "canvas") is True
