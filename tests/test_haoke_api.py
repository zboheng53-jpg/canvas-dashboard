from services import workspace as workspace_service

import pytest

import app as dashboard_app


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    monkeypatch.setattr(workspace_service, "user_dir", lambda username: user_dir)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


def test_haoke_todos_returns_stale_cache_and_starts_refresh(client_with_user, monkeypatch):
    fetched = []
    refreshed = []
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(
        dashboard_app,
        "get_haoke_cached_todos",
        lambda username: {
            "ok": True,
            "data": [{"id": 7, "title": "cached"}],
            "cached": True,
            "fetched_at": 123.0,
            "stale": True,
        },
    )
    monkeypatch.setattr(dashboard_app, "start_haoke_background_refresh", lambda username: refreshed.append(username) or True)
    # The endpoint reports the polling flag from the live refresh registry, not
    # from the cache snapshot it read before submitting the job.
    monkeypatch.setattr(dashboard_app, "is_haoke_refreshing", lambda username: bool(refreshed))
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: fetched.append(username) or {"ok": True, "data": []})
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    monkeypatch.setattr(dashboard_app, "save_haoke_state", lambda username, state: None)

    resp = client_with_user.get("/api/haoke/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["data"] == [{"id": 7, "title": "cached", "subtasks": []}]
    assert data["cached"] is True
    assert data["stale"] is True
    assert data["refreshing"] is True
    assert data["fetched_at"] == 123.0
    assert refreshed == ["alice"]
    assert fetched == []


def test_haoke_todos_reports_refreshing_when_stale_refresh_already_active(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(
        dashboard_app,
        "get_haoke_cached_todos",
        lambda username: {
            "ok": True,
            "data": [],
            "cached": True,
            "fetched_at": 123.0,
            "stale": True,
            "refreshing": True,
        },
    )
    monkeypatch.setattr(dashboard_app, "start_haoke_background_refresh", lambda username: False)
    monkeypatch.setattr(dashboard_app, "is_haoke_refreshing", lambda username: True)
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: pytest.fail("stale cache should not fetch"))
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})

    resp = client_with_user.get("/api/haoke/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["stale"] is True
    assert data["refreshing"] is True


def test_haoke_cache_only_reports_stopped_job_without_restarting_stale_refresh(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(dashboard_app, "get_haoke_cached_todos", lambda username: {
        "ok": True, "data": [], "cached": True, "stale": True, "refreshing": False})
    monkeypatch.setattr(dashboard_app, "start_haoke_background_refresh", lambda username: pytest.fail("poll must not restart a failed job"))
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: pytest.fail("poll must not contact upstream"))
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    result = client_with_user.get("/api/haoke/todos?cache_only=1").get_json()
    assert result["stale"] is True
    assert result["refreshing"] is False
    assert result["sync"]["refreshing"] is False


def test_haoke_todos_returns_fresh_cache_without_refresh(client_with_user, monkeypatch):
    refreshed = []
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(
        dashboard_app,
        "get_haoke_cached_todos",
        lambda username: {
            "ok": True,
            "data": [],
            "cached": True,
            "fetched_at": 456.0,
            "stale": False,
        },
    )
    monkeypatch.setattr(dashboard_app, "start_haoke_background_refresh", lambda username: refreshed.append(username) or True)
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: pytest.fail("fresh cache should not fetch"))
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})

    resp = client_with_user.get("/api/haoke/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["stale"] is False
    assert data["refreshing"] is False
    assert refreshed == []


def test_haoke_todos_returns_pending_when_cache_missing(client_with_user, monkeypatch):
    refreshed = []
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(dashboard_app, "get_haoke_cached_todos", lambda username: None)
    monkeypatch.setattr(dashboard_app, "start_haoke_background_refresh", lambda username: refreshed.append(username) or True)
    monkeypatch.setattr(dashboard_app, "is_haoke_refreshing", lambda username: bool(refreshed))
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: pytest.fail("cold cache must not fetch synchronously"))
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})

    resp = client_with_user.get("/api/haoke/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["data"] == []
    assert data["cached"] is True
    assert data["refreshing"] is True
    assert data["sync"]["refreshing"] is True
    assert refreshed == ["alice"]


def test_haoke_todos_adds_error_code_when_fetch_fails(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(dashboard_app, "get_haoke_cached_todos", lambda username: {"ok": False, "error": "network down", "data": []})
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})

    resp = client_with_user.get("/api/haoke/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is False
    assert data["code"] == "haoke_fetch_failed"
    assert data["error"] == "network down"



def test_haoke_todos_uses_setup_error_code_when_credentials_missing(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: False)
    monkeypatch.setattr(
        dashboard_app,
        "fetch_haoke_todos",
        lambda username: {"ok": False, "error": "setup required", "data": [], "need_setup": True},
    )
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})

    resp = client_with_user.get("/api/haoke/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is False
    assert data["need_setup"] is True
    assert data["code"] == "haoke_credentials_missing"


def test_haoke_config_validation_uses_error_code(client_with_user):
    resp = client_with_user.post(
        "/api/haoke/config",
        json={"username": "", "password": ""},
        headers=client_with_user.csrf_headers,
    )
    data = resp.get_json()

    assert resp.status_code == 400
    assert data["ok"] is False
    assert data["code"] == "haoke_credentials_required"
