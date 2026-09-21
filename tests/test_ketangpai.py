import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app as dashboard_app
import ketangpai_client
from storage import read_json_file, write_json_file


def _user_dir(root: Path):
    def resolve(username):
        path = root / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    return resolve


@pytest.fixture(autouse=True)
def clear_token_cache():
    ketangpai_client._token_cache.clear()
    yield
    ketangpai_client._token_cache.clear()


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    monkeypatch.setattr(ketangpai_client, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ketangpai_client, "KEY_FILE", tmp_path / ".encryption_key")
    monkeypatch.setattr(ketangpai_client, "user_dir", _user_dir(tmp_path))
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", _user_dir(tmp_path))
    return tmp_path


@pytest.fixture
def client_with_user(test_env):
    user_dir = test_env / "users" / "testuser"
    user_dir.mkdir(parents=True, exist_ok=True)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "testuser"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


# ---- Client Unit Tests ----

def test_token_encryption_and_storage(test_env):
    user = "alice"
    assert not ketangpai_client.has_token(user)

    ketangpai_client._save_token(user, "test_token_12345")
    assert ketangpai_client.has_token(user)
    assert ketangpai_client._get_token(user) == "test_token_12345"

    # Verify token is encrypted in config.json
    cfg = read_json_file(test_env / "users" / user / "config.json", {})
    assert "ketangpai_token_encrypted" in cfg
    assert cfg["ketangpai_token_encrypted"] != "test_token_12345"

    ketangpai_client.logout(user)
    assert not ketangpai_client.has_token(user)
    assert ketangpai_client._get_token(user) is None


def test_encrypt_password():
    plain = "my_secret_pwd_123"
    enc = ketangpai_client._encrypt_password(plain)
    assert enc != plain
    # Decrypt and verify
    import base64
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    raw = base64.b64decode(enc.encode("utf-8"))
    cipher = Cipher(algorithms.AES(b"ktp4567890123456"), modes.CBC(b"ktp4567890123456"))
    dec = cipher.decryptor()
    padded = dec.update(raw) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    unpadded = unpadder.update(padded) + unpadder.finalize()
    assert unpadded.decode("utf-8") == plain


def test_get_figure_code(monkeypatch):
    mock_post_resp = MagicMock()
    mock_post_resp.json.return_value = {
        "status": 1,
        "data": {
            "url": "https://openapiv5.ketangpai.com/UserApi/verify?sessionid=sess_123",
            "sessionid": "sess_123",
        },
    }
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.headers = {"Content-Type": "image/png"}
    mock_get_resp.content = b"\x89PNG\r\n\x1a\nfakeimagebytes"

    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kw: mock_post_resp)
    monkeypatch.setattr(ketangpai_client.requests, "get", lambda url, **kw: mock_get_resp)

    res = ketangpai_client.get_figure_code()
    assert res["ok"] is True
    assert res["sessionid"] == "sess_123"
    assert res["url"] == "https://openapiv5.ketangpai.com/UserApi/verify?sessionid=sess_123"
    assert res["image_data"].startswith("data:image/png;base64,")


def test_send_sms_success_and_errors(monkeypatch):
    # Success
    mock_ok = MagicMock()
    mock_ok.json.return_value = {"status": 1, "message": "success"}
    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kw: mock_ok)
    res = ketangpai_client.send_sms("13800000000", verify="42", sessionid="sess_123")
    assert res["ok"] is True

    # Error 30106 -> Graphical captcha error
    mock_err_30106 = MagicMock()
    mock_err_30106.json.return_value = {"status": 0, "code": 30106, "message": "验证码输入错误"}
    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kw: mock_err_30106)
    res = ketangpai_client.send_sms("13800000000", verify="wrong", sessionid="sess_123")
    assert res["ok"] is False
    assert "图形验证码计算错误" in res["error"]

    # Error 30117 -> Unregistered mobile
    mock_err_30117 = MagicMock()
    mock_err_30117.json.return_value = {"status": 0, "code": 30117, "message": "手机号未注册"}
    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kw: mock_err_30117)
    res = ketangpai_client.send_sms("13800000000", verify="42", sessionid="sess_123")
    assert res["ok"] is False
    assert "该手机号未在课堂派注册" in res["error"]


def test_phone_login_success(monkeypatch, test_env):
    user = "alice"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": 1,
        "message": "success",
        "data": {"token": "tok_mobile_abc"},
    }
    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kwargs: mock_resp)

    res = ketangpai_client.phone_login(user, "13800000000", "123456")
    assert res["ok"] is True
    assert ketangpai_client.has_token(user)
    assert ketangpai_client._get_token(user) == "tok_mobile_abc"


def test_phone_login_failure(monkeypatch, test_env):
    user = "alice"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": 0,
        "message": "验证码错误",
    }
    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kwargs: mock_resp)

    res = ketangpai_client.phone_login(user, "13800000000", "000000")
    assert res["ok"] is False
    assert "验证码错误" in res["error"]
    assert not ketangpai_client.has_token(user)


def test_password_login_success(monkeypatch, test_env):
    user = "alice"
    captured_payload = {}

    def mock_post(url, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json", {})
        resp = MagicMock()
        resp.json.return_value = {
            "status": 1,
            "message": "success",
            "data": {"token": "tok_pwd_xyz"},
        }
        return resp

    monkeypatch.setattr(ketangpai_client.requests, "post", mock_post)

    res = ketangpai_client.password_login(user, "test@example.com", "pass123")
    assert res["ok"] is True
    assert ketangpai_client.has_token(user)
    assert ketangpai_client._get_token(user) == "tok_pwd_xyz"
    # Verify encrypted password payload
    assert captured_payload.get("encryption") == 1
    assert captured_payload.get("password") != "pass123"
    assert captured_payload.get("email") == "test@example.com"


def test_fetch_courses_dedupes_and_formats(monkeypatch, test_env):
    user = "alice"
    ketangpai_client._save_token(user, "tok_valid")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": 1,
        "data": {
            "toplists": [
                {"id": "c1", "coursename": "Course 1", "classname": "Class A", "fixTerm": "202620271", "classending": "0"}
            ],
            "lists": [
                {"id": "c1", "coursename": "Course 1 duplicate", "classname": "Class A", "fixTerm": "202620271", "classending": "0"},
                {"id": "c2", "coursename": "Course 2", "classname": "Class B", "fixTerm": "202520262", "classending": "1"}
            ]
        }
    }
    monkeypatch.setattr(ketangpai_client.requests, "post", lambda url, **kwargs: mock_resp)

    res = ketangpai_client.fetch_courses(user)
    assert res["ok"] is True
    courses = res["courses"]
    assert len(courses) == 2
    assert courses[0]["id"] == "c1"
    assert courses[1]["id"] == "c2"


def test_fetch_assignments_filters_term_and_maps_todos(monkeypatch, test_env):
    user = "alice"
    ketangpai_client._save_token(user, "tok_valid")

    # Mock courses API
    def fake_post(url, **kwargs):
        resp = MagicMock()
        if "/courseApi/simpleLists" in url:
            resp.json.return_value = {
                "status": 1,
                "data": {
                    "toplists": [],
                    "lists": [
                        {"id": "c_active", "coursename": "Active Course", "fixTerm": "202620271", "classending": "0"},
                        {"id": "c_ended", "coursename": "Ended Course", "fixTerm": "202520261", "classending": "1"},
                    ]
                }
            }
            return resp

        if "/FutureV2/CourseMeans/getCourseContent" in url:
            payload = kwargs.get("json", {})
            cid = payload.get("courseid")
            ctype = payload.get("contenttype")
            if cid == "c_active" and ctype == 4:
                resp.json.return_value = {
                    "status": 1,
                    "data": {
                        "pageTotal": 1,
                        "lists": [
                            {
                                "id": "hw1",
                                "title": "Homework 1",
                                "endtime": "2026-09-22 23:59:00",
                                "createtime": "2026-09-15 10:00:00",
                                "mstatus": 0,
                                "state": 3,
                            },
                            {
                                "id": "hw_done",
                                "title": "Submitted Homework",
                                "endtime": "2026-09-20 23:59:00",
                                "createtime": "2026-09-15 10:00:00",
                                "mstatus": 1,
                                "state": 3,
                            }
                        ]
                    }
                }
            elif cid == "c_active" and ctype == 6:
                resp.json.return_value = {
                    "status": 1,
                    "data": {
                        "pageTotal": 1,
                        "lists": [
                            {
                                "id": "test1",
                                "title": "Quiz 1",
                                "endtime": "2026-09-25 18:00:00",
                                "createtime": "2026-09-15 10:00:00",
                                "submit_state": 0,
                            }
                        ]
                    }
                }
            else:
                resp.json.return_value = {"status": 1, "data": {"pageTotal": 0, "lists": []}}
            return resp

        resp.json.return_value = {"status": 0}
        return resp

    monkeypatch.setattr(ketangpai_client.requests, "post", fake_post)

    res = ketangpai_client.fetch_assignments(user, force_fetch=True)
    assert res["ok"] is True
    todos = res["items"]
    # Only pending/unsubmitted homework and test
    assert len(todos) == 2
    hw = next(t for t in todos if t["id"] == "ktp_hw_hw1")
    assert hw["title"] == "Homework 1"
    assert hw["course"] == "Active Course"
    assert hw["due_str"] == "09-22 23:59"
    assert hw["due_ts"] == "2026-09-22T23:59:00+08:00"
    assert hw["type"] == "作业"

    quiz = next(t for t in todos if t["id"] == "ktp_test_test1")
    assert quiz["title"] == "Quiz 1"
    assert quiz["type"] == "测验"

    # Verify cache written
    cache = read_json_file(test_env / "users" / user / "ketangpai_cache.json", {})
    assert "items" in cache
    assert len(cache["items"]) == 2


def test_state_actions(test_env):
    user = "alice"
    assert ketangpai_client.load_state(user) == {
        "hidden": [], "highlighted": [], "deleted": [], "completed": [], "overrides": {}
    }

    ketangpai_client.update_state(user, "hide", "hw1")
    state = ketangpai_client.load_state(user)
    assert "hw1" in state["hidden"]

    ketangpai_client.update_state(user, "unhide", "hw1")
    state = ketangpai_client.load_state(user)
    assert "hw1" not in state["hidden"]

    ketangpai_client.update_state(user, "complete", "hw1")
    state = ketangpai_client.load_state(user)
    assert "hw1" in state["completed"]

    ketangpai_client.update_override(user, "hw1", patch={"title": "Custom Title", "due_ts": "2026-09-30T12:00:00"})
    state = ketangpai_client.load_state(user)
    assert state["overrides"]["hw1"]["title"] == "Custom Title"
    assert state["overrides"]["hw1"]["due_ts"] == "2026-09-30T12:00:00"


# ---- Flask API Integration Tests ----

def test_api_ketangpai_config(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app, "has_ktp_token", lambda username: True)
    monkeypatch.setattr(
        dashboard_app,
        "fetch_ktp_courses",
        lambda username: {"ok": True, "courses": [{"id": "c1", "coursename": "力学原理A"}]},
    )

    resp = client_with_user.get("/api/ketangpai/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["has_token"] is True
    assert len(data["courses"]) == 1
    assert data["courses"][0]["coursename"] == "力学原理A"


def test_api_ketangpai_login_routes(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app, "ktp_phone_login", lambda username, phone, code: {"ok": True})
    monkeypatch.setattr(dashboard_app, "ktp_password_login", lambda username, account, password: {"ok": True})

    # SMS login
    resp = client_with_user.post(
        "/api/ketangpai/login",
        json={"phone": "13800000000", "code": "123456"},
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Password login
    resp = client_with_user.post(
        "/api/ketangpai/login-password",
        json={"account": "user1", "password": "secret"},
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_api_ketangpai_figure_code_and_send_sms(client_with_user, monkeypatch):
    monkeypatch.setattr(
        dashboard_app.ketangpai_client,
        "get_figure_code",
        lambda: {"ok": True, "sessionid": "s123", "url": "http://example.com/img.png", "image_data": "data:image/png;base64,abc"},
    )
    captured_sms = {}
    def mock_send_sms(phone, verify="", sessionid=""):
        nonlocal captured_sms
        captured_sms = {"phone": phone, "verify": verify, "sessionid": sessionid}
        return {"ok": True, "message": "验证码已发送"}

    monkeypatch.setattr(dashboard_app, "ktp_send_sms", mock_send_sms)

    # Figure code endpoint
    resp = client_with_user.get("/api/ketangpai/figure-code")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["sessionid"] == "s123"
    assert data["image_data"] == "data:image/png;base64,abc"

    # Send SMS endpoint
    resp = client_with_user.post(
        "/api/ketangpai/send-sms",
        json={"phone": "13800000000", "verify": "42", "sessionid": "s123"},
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert captured_sms == {"phone": "13800000000", "verify": "42", "sessionid": "s123"}


def test_api_clear_platform_data_and_override(client_with_user, test_env):
    user = "testuser"
    user_p = test_env / "users" / user

    ketangpai_client._save_token(user, "tok_clear_test")
    write_json_file(user_p / "ketangpai_cache.json", {"items": [{"id": "k1", "title": "Test"}]})
    write_json_file(user_p / "ketangpai_state.json", {"hidden": ["k1"], "highlighted": [], "deleted": [], "completed": [], "overrides": {}})

    assert (user_p / "ketangpai_cache.json").exists()
    assert ketangpai_client.has_token(user)

    # Test override
    resp = client_with_user.post(
        "/api/platform/ketangpai/override",
        json={"id": "k1", "title": "Renamed Task"},
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    state = ketangpai_client.load_state(user)
    assert state["overrides"]["k1"]["title"] == "Renamed Task"

    # Clear platform data
    resp = client_with_user.delete(
        "/api/platform/ketangpai/data",
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert not ketangpai_client.has_token(user)
    assert not (user_p / "ketangpai_cache.json").exists()


def test_agent_complete_ketangpai_todo(client_with_user, test_env):
    user = "testuser"
    user_p = test_env / "users" / user
    write_json_file(user_p / "ketangpai_cache.json", {"items": [{"id": "item100", "title": "Homework", "due_ts": "2026-09-22T23:59:00"}]})

    # Test completion helper
    ok = dashboard_app._complete_agent_todo(user, "item100", source="ketangpai")
    assert ok is True

    state = ketangpai_client.load_state(user)
    assert "item100" in state["completed"]


def test_ketangpai_frontend_login_entries():
    views_path = Path(__file__).parents[1] / "frontend" / "templates" / "dashboard" / "_placeholder_views.html"
    index_path = Path(__file__).parents[1] / "frontend" / "templates" / "index.html"
    views_html = views_path.read_text(encoding="utf-8")
    index_html = index_path.read_text(encoding="utf-8")

    # Platform navigation button exists
    assert 'data-od-id="connection-platform-ketangpai"' in views_html
    assert "课堂派" in views_html

    # Setup container is NOT hidden by default
    assert 'id="ktp-setup-inline" class="connection-stack"' in views_html
    assert 'id="ktp-setup-inline" class="hidden' not in views_html

    # SMS login inputs & buttons exist
    assert 'id="ktp-phone-inline"' in views_html
    assert 'id="ktp-send-sms-btn-inline"' in views_html
    assert 'id="ktp-captcha-inline"' in views_html
    assert 'onclick="sendKetangpaiSmsInline()"' in views_html
    assert 'onclick="doKetangpaiLoginInline()"' in views_html

    # Password login inputs & buttons exist
    assert 'id="ktp-toggle-login-mode-btn"' in views_html
    assert 'id="ktp-username-inline"' in views_html
    assert 'id="ktp-password-inline"' in views_html
    assert 'data-od-id="ketangpai-password-login"' in views_html

    # index.html JS handles ketangpai properly
    assert "loadKetangpaiStatusInline" in index_html
    assert "toggleKtpLoginModeInline" in index_html
    assert "setupDiv.classList.remove('hidden')" in index_html

