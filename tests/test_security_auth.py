from services import workspace as workspace_service

import pytest

import app as dashboard_app
import user_paths

LOGIN_ATTEMPTS = 8
REGISTER_ATTEMPTS = 5
SMS_ATTEMPTS = 3


def _set_csrf(client, token="csrf-test-token"):
    with client.session_transaction() as sess:
        sess["_csrf_token"] = token
    return {"X-CSRF-Token": token}


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "custom_todos.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    monkeypatch.setattr(workspace_service, "user_dir", lambda username: user_dir)
    if hasattr(dashboard_app, "_rate_limit_buckets"):
        dashboard_app._rate_limit_buckets.clear()
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
        yield client


@pytest.fixture
def anonymous_client(monkeypatch):
    if hasattr(dashboard_app, "_rate_limit_buckets"):
        dashboard_app._rate_limit_buckets.clear()
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        yield client


@pytest.fixture
def isolated_auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app.auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app.auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(dashboard_app.auth, "SECRET_KEY_FILE", tmp_path / ".flask_secret_key")
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    if hasattr(dashboard_app, "_rate_limit_buckets"):
        dashboard_app._rate_limit_buckets.clear()
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        yield client


def test_session_cookie_defaults_are_hardened():
    assert dashboard_app.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert dashboard_app.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert dashboard_app.app.config["SESSION_COOKIE_SECURE"] is False


def test_public_auth_pages_show_icp_footer(anonymous_client, monkeypatch):
    monkeypatch.setattr(dashboard_app.settings, "ICP_NUMBER", "闽ICP备2026026558号-1")

    for path in ("/login", "/register"):
        response = anonymous_client.get(path)

        assert response.status_code == 200
        assert "闽ICP备2026026558号-1" in response.get_data(as_text=True)
        assert "https://beian.miit.gov.cn/" in response.get_data(as_text=True)


def test_wrong_password_returns_readable_login_error(anonymous_client, monkeypatch):
    monkeypatch.setattr(dashboard_app.auth, "verify_login", lambda username, password: False)
    headers = _set_csrf(anonymous_client)

    response = anonymous_client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "用户名或密码错误"


def test_mutating_api_requires_csrf_token(client_with_user):
    resp = client_with_user.post(
        "/api/custom/todos",
        json={"text": "CSRF should block this"},
    )

    assert resp.status_code == 403
    assert resp.get_json()["ok"] is False


def test_mutating_api_accepts_valid_csrf_token(client_with_user):
    headers = _set_csrf(client_with_user)

    resp = client_with_user.post(
        "/api/custom/todos",
        json={"text": "Allowed with token"},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_login_endpoint_rate_limits_by_ip_and_username(anonymous_client, monkeypatch):
    headers = _set_csrf(anonymous_client)
    monkeypatch.setattr(dashboard_app.auth, "verify_login", lambda username, password: False)

    last = None
    for _ in range(LOGIN_ATTEMPTS + 1):
        last = anonymous_client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong"},
            headers=headers,
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

    assert last.status_code == 429
    assert last.get_json()["ok"] is False


def test_register_endpoint_rate_limits_by_ip_and_username(anonymous_client, monkeypatch):
    headers = _set_csrf(anonymous_client)
    monkeypatch.setattr(dashboard_app.auth, "register", lambda username, password: (False, "bad"))

    last = None
    for _ in range(REGISTER_ATTEMPTS + 1):
        last = anonymous_client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password1"},
            headers=headers,
            environ_base={"REMOTE_ADDR": "203.0.113.11"},
        )

    assert last.status_code == 429
    assert last.get_json()["ok"] is False


def test_auth_register_rejects_non_json_request(isolated_auth_client):
    headers = _set_csrf(isolated_auth_client)

    resp = isolated_auth_client.post(
        "/api/auth/register",
        data="username=alice",
        content_type="text/plain",
        headers=headers,
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_auth_login_rejects_non_json_request(isolated_auth_client):
    headers = _set_csrf(isolated_auth_client)

    resp = isolated_auth_client.post(
        "/api/auth/login",
        data="username=alice",
        content_type="text/plain",
        headers=headers,
    )

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_register_rejects_weak_password_and_duplicate_username(isolated_auth_client):
    headers = _set_csrf(isolated_auth_client)

    weak = isolated_auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "12345"},
        headers=headers,
    )
    first = isolated_auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "123456"},
        headers=headers,
    )
    duplicate = isolated_auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "123456"},
        headers=headers,
    )

    assert weak.status_code == 400
    assert weak.get_json()["ok"] is False
    assert "6 位" in weak.get_json()["error"]
    assert first.status_code == 200
    assert first.get_json() == {"ok": True}
    assert duplicate.status_code == 400
    assert duplicate.get_json()["ok"] is False


def test_register_validation_error_is_sent_as_utf8_chinese(isolated_auth_client):
    response = isolated_auth_client.post(
        "/api/auth/register",
        json={"username": "x", "password": "strong-password"},
        headers=_set_csrf(isolated_auth_client),
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "用户名需为 3-20 位字母、数字或下划线" in body
    assert "\\u7528" not in body


def test_unauthenticated_api_returns_401_and_page_redirects_to_login(anonymous_client):
    api_resp = anonymous_client.get("/api/clock")
    page_resp = anonymous_client.get("/")

    assert api_resp.status_code == 401
    assert api_resp.get_json()["ok"] is False
    assert page_resp.status_code == 302
    assert page_resp.headers["Location"] == "/login"


def test_logout_clears_session_and_blocks_next_api_call(client_with_user):
    headers = _set_csrf(client_with_user)

    logout_resp = client_with_user.post("/api/auth/logout", headers=headers)
    api_resp = client_with_user.get("/api/clock")

    assert logout_resp.status_code == 200
    assert logout_resp.get_json() == {"ok": True}
    assert api_resp.status_code == 401


def test_successful_register_sets_persistent_session_cookie(isolated_auth_client):
    headers = _set_csrf(isolated_auth_client)

    resp = isolated_auth_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "strong-password"},
        headers=headers,
    )

    cookie = resp.headers.get("Set-Cookie", "")
    assert resp.status_code == 200
    assert "session=" in cookie
    assert "Expires=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_send_sms_rate_limits_by_ip_and_phone(client_with_user, monkeypatch):
    headers = _set_csrf(client_with_user)
    calls = []
    monkeypatch.setattr(
        dashboard_app,
        "send_sms",
        lambda phone: calls.append(phone) or {"ok": True},
    )

    last = None
    for _ in range(SMS_ATTEMPTS + 1):
        last = client_with_user.post(
            "/api/zhixuemeng/send-sms",
            json={"phone": "13800138000"},
            headers=headers,
            environ_base={"REMOTE_ADDR": "203.0.113.12"},
        )

    assert last.status_code == 429
    assert calls == ["13800138000"] * SMS_ATTEMPTS


def test_request_ip_uses_nginx_real_ip_not_client_forwarded_header():
    with dashboard_app.app.test_request_context(
        "/",
        headers={
            "X-Forwarded-For": "198.51.100.200",
            "X-Real-IP": "203.0.113.9",
        },
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
        assert dashboard_app._request_ip() == "203.0.113.9"


def test_canvas_config_returns_validation_error(client_with_user, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "save_feed_url",
        lambda username, url: (False, "calendar feed URL must resolve to public addresses"),
    )

    resp = client_with_user.post(
        "/api/config",
        json={"calendar_feed_url": "https://127.0.0.1/feed.ics"},
        headers=_set_csrf(client_with_user),
    )

    assert resp.status_code == 400
    assert resp.get_json() == {
        "ok": False,
        "error": "calendar feed URL must resolve to public addresses",
    }


def test_public_auth_pages_render_product_landing_showcase_and_privacy_link(
    anonymous_client, monkeypatch
):
    monkeypatch.setattr(dashboard_app.settings, "ICP_NUMBER", "闽ICP备2026026558号-1")

    expected_fragments = (
        "多平台作业与日程面板",
        "自动同步多平台作业与学校课表，整合长期规划。剥离杂音，一眼看清今天该做什么。",
        "待办清单",
        "长期项目",
        "今日日程",
        "数据如何保存",
        "今天要做什么，一眼清楚。",
        "Canvas",
        "好课",
        "智学盟",
        "智慧树",
        "课堂派",
        "同济OJ",
        "同济一网通办课表",
        "数据与隐私中心",
        'href="/privacy"',
        'href="https://github.com/zboheng53-jpg/canvas-dashboard"',
        "闽ICP备2026026558号-1",
    )

    login_html = anonymous_client.get("/login").get_data(as_text=True)
    for fragment in expected_fragments:
        assert fragment in login_html
    assert 'id="login-form"' in login_html
    assert 'id="login-username"' in login_html
    assert 'id="login-password"' in login_html

    register_html = anonymous_client.get("/register").get_data(as_text=True)
    for fragment in expected_fragments:
        assert fragment in register_html
    assert 'id="register-form"' in register_html
    assert 'id="register-username"' in register_html
    assert 'id="register-password"' in register_html


def test_dashboard_sidebar_renders_github_repository_link(client_with_user):
    html = client_with_user.get("/").get_data(as_text=True)
    assert 'class="sidebar-github-link"' in html
    assert 'href="https://github.com/zboheng53-jpg/canvas-dashboard"' in html
    assert 'class="sidebar-privacy-link"' in html
    assert 'href="/privacy"' in html



def test_public_privacy_and_welcome_pages_are_accessible_without_login(
    anonymous_client, monkeypatch
):
    monkeypatch.setattr(dashboard_app.settings, "ICP_NUMBER", "闽ICP备2026026558号-1")

    privacy_resp = anonymous_client.get("/privacy")
    assert privacy_resp.status_code == 200
    privacy_html = privacy_resp.get_data(as_text=True)
    for question in ("保存什么？", "为什么保存？", "保存在哪里？", "怎么删除？"):
        assert question in privacy_html
    assert 'href="/login"' in privacy_html
    assert "闽ICP备2026026558号-1" in privacy_html

    welcome_resp = anonymous_client.get("/welcome")
    assert welcome_resp.status_code == 200
    assert "今天要做什么，一眼清楚。" in welcome_resp.get_data(as_text=True)


def test_authenticated_privacy_and_welcome_routes(client_with_user):
    authed_privacy_html = client_with_user.get("/privacy").get_data(as_text=True)
    assert 'href="/"' in authed_privacy_html

    authed_welcome_resp = client_with_user.get("/welcome")
    assert authed_welcome_resp.status_code == 302
    assert authed_welcome_resp.headers["Location"] == "/"

