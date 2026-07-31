from urllib.parse import parse_qs, urlparse

import pytest

import app as dashboard_app
import zhihuishu_store
import zhihuishu_login_sessions


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app.auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(zhihuishu_login_sessions, "DATA_DIR", tmp_path)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


def test_zhihuishu_todos_requires_setup_when_no_session(client_with_user):
    resp = client_with_user.get("/api/zhihuishu/todos")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is False
    assert data["need_setup"] is True


def test_zhihuishu_state_rejects_json_null(client_with_user):
    resp = client_with_user.post(
        "/api/zhihuishu/state",
        data="null",
        content_type="application/json",
        headers=client_with_user.csrf_headers,
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_login_page_accepts_zhihuishu(client_with_user):
    resp = client_with_user.get("/login/zhihuishu")

    assert resp.status_code == 200
    assert "取消当前登录会话".encode("utf-8") in resp.data


def test_create_login_session_returns_user_url(client_with_user, monkeypatch):
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "create_session",
        lambda username: {
            "username": username,
            "token": "tok_123456789012",
            "port": 6107,
            "url": "/zhihuishu/session/tok_123456789012/",
            "expires_at": 2000,
        },
    )

    resp = client_with_user.post("/api/zhihuishu/login-session", headers=client_with_user.csrf_headers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["url"] == "/zhihuishu/session/tok_123456789012/"
    assert data["token"] == "tok_123456789012"


def test_zhihuishu_config_reports_active_login_session(client_with_user, monkeypatch):
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "load_session",
        lambda username: {
            "username": username,
            "token": "tok_123456789012",
            "port": 6107,
            "created_at": 1000,
            "expires_at": 1600,
        },
    )

    resp = client_with_user.get("/api/zhihuishu/config")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["login_session"]["active"] is True
    assert data["login_session"]["expires_at"] == 1600
    assert "token" not in data["login_session"]


def test_cancel_current_login_session_without_token(client_with_user, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "stop_session",
        lambda username, token=None: stopped.append((username, token)) or True,
    )

    resp = client_with_user.delete("/api/zhihuishu/login-session", headers=client_with_user.csrf_headers)

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert stopped == [("alice", None)]


def test_vnc_auth_rejects_invalid_token(client_with_user):
    resp = client_with_user.get("/api/zhihuishu/login-session-auth?token=bad&port=6107")

    assert resp.status_code == 401


def test_vnc_auth_rejects_token_for_other_user(client_with_user, monkeypatch):
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "session_for_token",
        lambda token: {
            "username": "bob",
            "token": token,
            "port": 6107,
            "expires_at": 2000,
        },
    )
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "validate_session",
        lambda token, port: True,
    )

    resp = client_with_user.get("/api/zhihuishu/login-session-auth?token=tok_123456789012&port=6107")

    assert resp.status_code == 401


def test_login_session_redirect_uses_tokenized_proxy(client_with_user, monkeypatch):
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "session_for_token",
        lambda token: {
            "username": "alice",
            "token": token,
            "port": 6107,
            "expires_at": 2000,
        },
    )
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "validate_session",
        lambda token, port: True,
    )

    resp = client_with_user.get("/zhihuishu/session/tok_123456789012/")

    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert "/zhs-vnc/6107/tok_123456789012/vnc.html" in location
    assert parse_qs(urlparse(location).query)["path"] == [
        "zhs-vnc/6107/tok_123456789012/websockify"
    ]


def test_complete_login_stops_container_and_refreshes_cache(client_with_user, monkeypatch):
    stopped = []
    refreshed = []

    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "session_for_token",
        lambda token: {
            "username": "alice",
            "token": token,
            "port": 6107,
            "expires_at": 2000,
        },
    )
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "stop_session",
        lambda username, token: stopped.append((username, token)) or True,
    )
    def refresh(username, force_fetch=False):
        refreshed.append((username, force_fetch))
        zhihuishu_store.save_cache(username, [{"id": "zhs_1", "title": "作业"}], fetched_at=1234.0)
        zhihuishu_store.save_status(username, {
            "session": "active",
            "last_fetch_at": 1234.0,
            "last_success_at": 1234.0,
            "last_error": "",
        })
        return True

    monkeypatch.setattr(dashboard_app.zhihuishu_worker, "run_scheduled_cycle", refresh)

    resp = client_with_user.post(
        "/api/zhihuishu/login-session/tok_123456789012/complete",
        headers=client_with_user.csrf_headers,
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert stopped == [("alice", "tok_123456789012")]
    assert refreshed == [("alice", True)]
    assert zhihuishu_store.load_cache("alice")["items"] == [{"id": "zhs_1", "title": "作业"}]
