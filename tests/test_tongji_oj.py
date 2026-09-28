import base64
import time
from threading import Event
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import app as dashboard_app
import external_subtasks
import tongji_oj_client
import platform_sync
from storage import read_json_file, write_json_file


def _user_dir(root: Path):
    def resolve(username):
        path = root / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    return resolve


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    monkeypatch.setattr(tongji_oj_client, "DATA_DIR", tmp_path)
    monkeypatch.setattr(tongji_oj_client, "KEY_FILE", tmp_path / ".encryption_key")
    monkeypatch.setattr(tongji_oj_client, "user_dir", _user_dir(tmp_path))
    monkeypatch.setattr(tongji_oj_client, "_cookie_cache", {})
    monkeypatch.setattr(tongji_oj_client, "_refresh_jobs", {})
    monkeypatch.setattr(platform_sync, "user_dir", _user_dir(tmp_path))
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


SAMPLE_ASSIGNMENTS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Assignments - Tongji Online Judge</title></head>
<body>
<div id="main_container">
  <h2 id="course_btn" data-id="1"><a>1: community</a></h2>
  <div id="course1">
    <table class="sharif_table">
      <thead>
        <tr>
          <th>Assignment</th><th>Plan</th><th>Problems</th>
          <th>Submissions</th><th>Coefficient</th><th>Start Time</th><th>Finish Time</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>编程基础题库</td>
          <td>Default</td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/problems_list/3">10 problems</a></td>
          <td>1000 submissions</td>
          <td>100%</td>
          <td>2020-01-01 00:00:00</td>
          <td>2099-01-01 00:00:00</td>
          <td>Open</td>
        </tr>
      </tbody>
    </table>
  </div>

  <h2 id="course_btn" data-id="45"><a>45: 2026秋数据结构与算法设计（刘春梅）</a></h2>
  <div id="course45">
    <table class="sharif_table">
      <thead>
        <tr>
          <th>Assignment</th><th>Plan</th><th>Problems</th>
          <th>Submissions</th><th>Coefficient</th><th>Start Time</th><th>Finish Time</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>HW1线性表</td>
          <td>Default</td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/problems_list/590">5 problems</a></td>
          <td>124 submissions</td>
          <td>100%</td>
          <td>2026-09-25 18:00:00</td>
          <td>2026-10-08 23:59:59</td>
          <td>Open</td>
        </tr>
        <tr>
          <td>HW0编程基础</td>
          <td>Default</td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/problems_list/554">2 problems</a></td>
          <td>320 submissions</td>
          <td>100%</td>
          <td>2026-09-12 00:00:00</td>
          <td>2026-12-31 00:00:00</td>
          <td>Open</td>
        </tr>
        <tr>
          <td>已关闭作业</td>
          <td>Default</td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/problems_list/400">3 problems</a></td>
          <td>50 submissions</td>
          <td>0%</td>
          <td>2026-09-01 00:00:00</td>
          <td>2026-09-10 23:59:59</td>
          <td>Closed</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
</body>
</html>
"""

def test_credentials_and_cookies_encryption(test_env):
    user = "alice"
    assert not tongji_oj_client.has_token(user)

    tongji_oj_client.save_credentials(user, "2559999", "my_secret_pwd", login_mode="iam")
    assert tongji_oj_client.has_token(user)

    creds = tongji_oj_client.load_credentials(user)
    assert creds == {"username": "2559999", "password": "my_secret_pwd", "login_mode": "iam"}

    tongji_oj_client._save_cookies(user, {"shj_session": "sess_abc"})
    assert tongji_oj_client._load_cookies(user) == {"shj_session": "sess_abc"}

    cfg = read_json_file(test_env / "users" / user / "config.json", {})
    assert "tongjioj_credentials_encrypted" in cfg
    assert "my_secret_pwd" not in cfg["tongjioj_credentials_encrypted"]
    assert "tongjioj_cookies_encrypted" in cfg
    assert "sess_abc" not in cfg["tongjioj_cookies_encrypted"]

    tongji_oj_client.logout(user)
    assert not tongji_oj_client.has_token(user)
    assert tongji_oj_client.load_credentials(user) is None
    assert tongji_oj_client._load_cookies(user) is None


def test_parse_assignments_and_build_todos():
    courses, assignments = tongji_oj_client.parse_assignments_html(SAMPLE_ASSIGNMENTS_HTML)
    assert courses == [{"id": "45", "name": "2026秋数据结构与算法设计（刘春梅）"}]
    assert len(assignments) == 3

    todos_all_pending = tongji_oj_client.build_assignment_todos(assignments)
    # Skips community (id=1) and Closed (id=400), returns HW1线性表 (590) and HW0编程基础 (554)
    assert [t["id"] for t in todos_all_pending] == ["tjoj_590", "tjoj_554"]
    hw1 = todos_all_pending[0]
    assert hw1["title"] == "HW1线性表"
    assert hw1["course"] == "2026秋数据结构与算法设计（刘春梅）"
    assert hw1["due_str"] == "10-08 23:59"
    assert hw1["due_ts"] == "2026-10-08T23:59:59+08:00"
    assert hw1["type"] == "编程作业"
    assert hw1["problem_count"] == 5
    assert "submitted_count" not in hw1
    assert hw1["url"] == "https://oj.tongji.edu.cn/index.php/assignments"

    # Submission totals on the assignment page never determine completion.
    assert assignments[1]["submissions_text"] == "320 submissions"
    assert [t["id"] for t in tongji_oj_client.build_assignment_todos(assignments, "45")] == ["tjoj_590", "tjoj_554"]
    assert tongji_oj_client.build_assignment_todos(assignments, "46") == []


def test_parse_raw_html_without_tbody_and_cache_version_upgrade(test_env):
    raw_asg_html_no_tbody = """
    <h2 id="course_btn" data-id="45"><a href="#">2026秋数据结构与算法设计（刘春梅）</a></h2>
    <div id="course45" style="display:none">
      <table class="sharif_table">
        <thead>
          <tr><th>Name</th><th>Plan</th><th>Problems</th><th>Submissions</th><th>Coefficient</th><th>Start Time</th><th>Finish Time</th><th>Status</th><th>PDF</th><th>Actions</th></tr>
        </thead>
        <tr>
          <td dir="auto">HW1线性表</td>
          <td> normal </td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/problems_list/3815">5 problems</a></td>
          <td>191 submissions</td>
          <td>100 %</td>
          <td>2026-09-22 00:00:00</td>
          <td>2026-10-08 23:59:59</td>
          <td><span style="color: green;">Open</span></td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/pdf/3815">PDF</a></td>
          <td></td>
        </tr>
        <tr>
          <td dir="auto">HW0编程基础 </td>
          <td> normal </td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/problems_list/3375">2 problems</a></td>
          <td>263 submissions</td>
          <td>100 %</td>
          <td>2026-09-12 00:00:00</td>
          <td>2026-12-31 00:00:00</td>
          <td><span style="color: green;">Open</span></td>
          <td><a href="https://oj.tongji.edu.cn/index.php/assignments/pdf/3375">PDF</a></td>
          <td></td>
        </tr>
      </table>
    </div>
    """
    courses, assignments = tongji_oj_client.parse_assignments_html(raw_asg_html_no_tbody)
    assert courses == [{"id": "45", "name": "2026秋数据结构与算法设计（刘春梅）"}]
    assert len(assignments) == 2
    todos = tongji_oj_client.build_assignment_todos(assignments)
    assert [t["id"] for t in todos] == ["tjoj_3815", "tjoj_3375"]
    assert todos[0]["title"] == "HW1线性表"
    assert "submitted_count" not in todos[0]
    assert todos[0]["problem_count"] == 5

    # Unversioned legacy cache should not be treated as fresh
    assert not tongji_oj_client._is_cache_fresh({"items": [], "updated_at": "2099-01-01T00:00:00+08:00"})


@pytest.mark.parametrize("fetch", ["fetch_assignments", "fetch_courses"])
def test_fetch_assignments_strictly_read_only_and_never_opens_problems(monkeypatch, test_env, fetch):
    user = "alice"
    tongji_oj_client._save_cookies(user, {"shjsession": "valid_sess"})
    requested_urls = []

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.cookies = requests.cookies.RequestsCookieJar()
            self.cookies.set("shjsession", "valid_sess", domain="oj.tongji.edu.cn", path="/")

        def get(self, url, **kwargs):
            requested_urls.append(("GET", url))
            resp = MagicMock()
            resp.status_code = 200
            resp.url = url
            assert url == tongji_oj_client.OJ_ASSIGNMENTS_URL
            resp.text = SAMPLE_ASSIGNMENTS_HTML
            return resp

        def post(self, url, **kwargs):
            requested_urls.append(("POST", url))
            raise AssertionError(f"Unexpected POST during read-only fetch: {url}")

    monkeypatch.setattr(tongji_oj_client.requests, "Session", FakeSession)

    res = (tongji_oj_client.fetch_assignments(user, force_fetch=True) if fetch == "fetch_assignments"
           else tongji_oj_client.fetch_courses(user))
    assert res["ok"] is True
    if fetch == "fetch_assignments":
        assert [it["id"] for it in res["items"]] == ["tjoj_590", "tjoj_554"]
    assert len(res["courses"]) == 1

    # Assignment synchronization must never request final submissions or problem pages.
    assert requested_urls == [("GET", tongji_oj_client.OJ_ASSIGNMENTS_URL)]
    assert all(method == "GET" for method, _ in requested_urls)
    assert all("problems_list" not in url and "/problems/" not in url and "submit" not in url for _, url in requested_urls)


def test_oj_cookie_rotation_replaces_restored_session():
    session = requests.Session()
    tongji_oj_client._restore_oj_cookies(session, {"shjsession": "old"})
    session.cookies.set("shjsession", "rotated", domain="oj.tongji.edu.cn", path="/")
    header = session.prepare_request(requests.Request("GET", tongji_oj_client.OJ_ASSIGNMENTS_URL)).headers["Cookie"]
    assert header == "shjsession=rotated"


def test_oj_assignment_timeout_retries_only_the_assignment_list(monkeypatch, test_env):
    user = "retry"
    tongji_oj_client._save_cookies(user, {"shjsession": "session"})
    session = requests.Session()
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs["timeout"]))
        if len(calls) == 1:
            raise requests.ReadTimeout()
        response = requests.Response()
        response.status_code, response.url = 200, url
        response._content = b"<html></html>"
        return response
    monkeypatch.setattr(session, "get", get)
    monkeypatch.setattr(tongji_oj_client.requests, "Session", lambda: session)
    monkeypatch.setattr(tongji_oj_client, "iam_login", lambda *args: pytest.fail("network timeout must not trigger login"))
    assert tongji_oj_client._fetch_authenticated_assignments(user) == ("<html></html>", None)
    assert [url for url, _ in calls] == [tongji_oj_client.OJ_ASSIGNMENTS_URL] * 2
    assert all(timeout == (8, tongji_oj_client.settings.TONGJIOJ_READ_TIMEOUT_SECONDS) for _, timeout in calls)


def test_exhausted_oj_timeout_is_one_confirmed_failure_and_keeps_cache(client_with_user, monkeypatch):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password", cookies={"shjsession": "session"})
    tongji_oj_client._save_cache_payload(user, [{"id": "keep", "title": "Keep homework"}], [])
    calls = []
    def timeout(self, url, **kwargs):
        calls.append(url)
        raise requests.ReadTimeout()
    monkeypatch.setattr(requests.Session, "get", timeout)
    client_with_user.get("/api/tongjioj/todos?refresh=1")
    result = _wait_for_refresh(client_with_user)
    assert len(calls) == 2
    assert result["data"][0]["title"] == "Keep homework"
    assert result["sync"]["error_code"] == "upstream_timeout"
    assert result["sync"]["consecutive_failures"] == 1


def test_renewed_oj_cookie_is_saved_after_assignment_page(monkeypatch, test_env):
    user = "renew"
    tongji_oj_client.save_credentials(user, "student", "password", cookies={"shjsession": "expired"})
    session = requests.Session()
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        response = requests.Response()
        response.status_code = 200
        response.url = tongji_oj_client.OJ_LOGIN_URL if len(calls) == 1 else url
        response._content = b"<html></html>"
        if len(calls) == 2:
            session.cookies.set("shjsession", "rotated", domain="oj.tongji.edu.cn", path="/")
        return response
    def login(*args):
        tongji_oj_client._save_cookies(user, {"shjsession": "renewed"})
        return {"ok": True}
    monkeypatch.setattr(session, "get", get)
    monkeypatch.setattr(tongji_oj_client.requests, "Session", lambda: session)
    monkeypatch.setattr(tongji_oj_client, "iam_login", login)
    assert tongji_oj_client._fetch_authenticated_assignments(user)[1] is None
    assert calls == [tongji_oj_client.OJ_ASSIGNMENTS_URL] * 2
    assert tongji_oj_client._load_cookies(user)["shjsession"] == "rotated"
    assert len(session.cookies) == 1


def test_selected_course_uses_fresh_cache_without_network(monkeypatch, test_env):
    user = "alice"
    tongji_oj_client.save_credentials(user, "student", "password")
    tongji_oj_client.set_selected_course(user, "45")
    tongji_oj_client._save_cache_payload(user, [
        {"id": "tjoj_1", "course_id": "45"},
        {"id": "tjoj_2", "course_id": "46"},
    ], [])
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", lambda username: pytest.fail("fresh cache must not fetch OJ"))

    result = tongji_oj_client.fetch_assignments(user)
    assert result["cached"] is True
    assert [item["id"] for item in result["items"]] == ["tjoj_1"]


def test_cache_only_api_returns_stale_filtered_state_without_network(client_with_user, monkeypatch, test_env):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password")
    tongji_oj_client.set_selected_course(user, "45")
    write_json_file(tongji_oj_client._cache_file(user), {
        "version": tongji_oj_client.CACHE_SCHEMA_VERSION,
        "updated_at": (datetime.now(tongji_oj_client.CST) - timedelta(hours=1)).isoformat(),
        "items": [{"id": "tjoj_1", "course_id": "45", "title": "OJ task"}, {"id": "tjoj_2", "course_id": "46"}],
        "courses": [],
    })
    tongji_oj_client.update_override(user, "tjoj_1", patch={"title": "Local title"})
    tongji_oj_client.update_state(user, "complete", "tjoj_1")
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", lambda username: pytest.fail("cache-only API must not fetch OJ"))

    result = client_with_user.get("/api/tongjioj/todos?cache_only=1").get_json()
    assert result["ok"] and result["cached"] and result["stale"] and result["has_cache"]
    assert [(item["id"], item["title"], item["done"]) for item in result["data"]] == [("tjoj_1", "Local title", True)]


def test_cache_only_api_distinguishes_first_sync_from_empty_cache(client_with_user, monkeypatch, test_env):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password")
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", lambda username: pytest.fail("cache-only API must not fetch OJ"))
    result = client_with_user.get("/api/tongjioj/todos?cache_only=1").get_json()
    assert result["ok"] and not result["has_cache"] and result["stale"]
    tongji_oj_client._save_cache_payload(user, [], [])
    result = client_with_user.get("/api/tongjioj/todos?cache_only=1").get_json()
    assert result["has_cache"] and not result["stale"]


def test_force_refresh_failure_preserves_cache_and_records_error(client_with_user, monkeypatch, test_env):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password")
    tongji_oj_client._save_cache_payload(user, [{"id": "tjoj_1", "title": "Keep me"}], [])
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", lambda username: (None, "OJ unavailable"))
    result = client_with_user.get("/api/tongjioj/todos?refresh=1").get_json()
    assert result["ok"]
    assert result["data"][0]["title"] == "Keep me"
    result = _wait_for_refresh(client_with_user)
    assert result["sync"]["consecutive_failures"] == 1
    assert result["sync"]["error_message"] == "OJ unavailable"


def _wait_for_refresh(client):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get("/api/tongjioj/todos?cache_only=1").get_json()
        if not result["sync"]["refreshing"]:
            return result
        time.sleep(0.01)
    pytest.fail("OJ background refresh did not finish")


@pytest.mark.parametrize("completed", [True, False])
def test_assignment_only_refresh_preserves_legacy_manual_state_and_subtasks(client_with_user, monkeypatch, test_env, completed):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password")
    tongji_oj_client.set_selected_course(user, "45")
    # A fresh v2 cache may have omitted HW0 because of final submissions.
    write_json_file(tongji_oj_client._cache_file(user), {
        "version": 2, "updated_at": datetime.now(tongji_oj_client.CST).isoformat(),
        "items": [{"id": "tjoj_590", "title": "Old homework", "course_id": "45"}], "courses": [],
    })
    tongji_oj_client.update_state(user, "complete", "tjoj_590")
    if not completed:
        tongji_oj_client.update_state(user, "uncomplete", "tjoj_590")
    tongji_oj_client.update_state(user, "hide", "tjoj_554")
    tongji_oj_client.update_state(user, "highlight", "tjoj_590")
    tongji_oj_client.update_state(user, "delete", "tjoj_400")
    tongji_oj_client.update_override(user, "tjoj_590", patch={"title": "Local homework", "due_ts": "2099-10-09T23:59:59+08:00"})
    monkeypatch.setattr(external_subtasks, "user_dir", _user_dir(test_env))
    subtasks = [{"id": 1, "text": "Local step", "done": True, "due_date": None}]
    external_subtasks.save_subtasks(user, "tongjioj", "tjoj_590", subtasks)
    directory = test_env / "users" / user
    state_path, subtasks_path = directory / "tongjioj_state.json", directory / "external_subtasks.json"
    original_state, original_subtasks = state_path.read_bytes(), subtasks_path.read_bytes()
    started, release = Event(), Event()
    def get_assignments(username):
        assert username == user
        started.set()
        assert release.wait(3)
        return SAMPLE_ASSIGNMENTS_HTML, None
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", get_assignments)

    # The obsolete projection remains usable until its replacement is ready.
    snapshot = client_with_user.get("/api/tongjioj/todos?cache_only=1").get_json()
    assert snapshot["stale"] and snapshot["has_cache"]
    assert bool(snapshot["data"][0].get("done")) is completed
    try:
        client_with_user.get("/api/tongjioj/todos")
        assert started.wait(2)
        assert state_path.read_bytes() == original_state
        assert subtasks_path.read_bytes() == original_subtasks
    finally:
        release.set()
        result = _wait_for_refresh(client_with_user)

    assert [item["id"] for item in result["data"]] == ["tjoj_590", "tjoj_554"]
    first = result["data"][0]
    assert bool(first.get("done")) is completed
    assert first["title"] == "Local homework"
    assert first["due_ts"] == "2099-10-09T23:59:59+08:00"
    assert first["subtasks"] == subtasks
    assert result["hidden"] == ["tjoj_554"] and result["highlighted"] == ["tjoj_590"]
    assert result["deleted"] == ["tjoj_400"]
    assert state_path.read_bytes() == original_state
    assert subtasks_path.read_bytes() == original_subtasks
    assert read_json_file(tongji_oj_client._cache_file(user), {})["version"] == tongji_oj_client.CACHE_SCHEMA_VERSION

    # Completing or undoing after the upgrade still survives another refresh.
    response = client_with_user.post("/api/tongjioj/state", json={
        "action": "uncomplete" if completed else "complete", "id": "tjoj_590",
    }, headers=client_with_user.csrf_headers)
    assert response.status_code == 200
    changed_state = state_path.read_bytes()
    client_with_user.get("/api/tongjioj/todos?refresh=1")
    result = _wait_for_refresh(client_with_user)
    assert bool(result["data"][0].get("done")) is not completed
    assert state_path.read_bytes() == changed_state
    assert subtasks_path.read_bytes() == original_subtasks


@pytest.mark.parametrize("clear", [False, True])
def test_background_refresh_cannot_restore_credentials_or_cache_after_disconnect(client_with_user, monkeypatch, test_env, clear):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password")
    started, release, finished = Event(), Event(), Event()
    original_worker = tongji_oj_client._run_background_refresh
    def observed_worker(username, job):
        try:
            original_worker(username, job)
        finally:
            finished.set()
    def old_fetch(username, **kwargs):
        started.set()
        assert release.wait(5)
        tongji_oj_client.save_credentials(username, "old-student", "old-password", cookies={"session": "old-cookie"})
        tongji_oj_client._save_cache_payload(username, [{"id": "old"}], [])
        return {"ok": True, "cached": False}
    monkeypatch.setattr(tongji_oj_client, "_run_background_refresh", observed_worker)
    monkeypatch.setattr(tongji_oj_client, "fetch_assignments", old_fetch)
    try:
        result = client_with_user.get("/api/tongjioj/todos?refresh=1").get_json()
        assert result["sync"]["refreshing"] and started.wait(1)
        if clear:
            response = client_with_user.delete("/api/platform/tongjioj/data", headers=client_with_user.csrf_headers)
        else:
            response = client_with_user.post("/api/tongjioj/logout", headers=client_with_user.csrf_headers)
        assert response.status_code == 200
    finally:
        release.set()
        assert finished.wait(2)
    assert not tongji_oj_client.has_credentials(user)
    assert user not in tongji_oj_client._cookie_cache
    assert not tongji_oj_client._cache_file(user).exists()


def test_background_refresh_preserves_cache_while_renewing_session(client_with_user, monkeypatch, test_env):
    user = "testuser"
    tongji_oj_client.save_credentials(user, "student", "password")
    tongji_oj_client._save_cache_payload(user, [{"id": "keep", "title": "Keep while logging in"}], [])
    started, release = Event(), Event()
    def renewing_fetch(username, **kwargs):
        tongji_oj_client.save_credentials(username, "student", "password", cookies={"session": "renewed"})
        started.set()
        assert release.wait(5)
        return {"ok": False, "error": "Upstream failed"}
    monkeypatch.setattr(tongji_oj_client, "fetch_assignments", renewing_fetch)
    try:
        client_with_user.get("/api/tongjioj/todos?refresh=1")
        assert started.wait(1)
        result = client_with_user.get("/api/tongjioj/todos?cache_only=1").get_json()
        assert result["data"][0]["title"] == "Keep while logging in"
        assert result["sync"]["refreshing"]
    finally:
        release.set()
        _wait_for_refresh(client_with_user)


def test_rsa_encrypt_password():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    b64_der = "".join(
        line.strip() for line in public_pem.splitlines() if not line.startswith("-----")
    )

    encrypted_b64 = tongji_oj_client._encrypt_rsa_password("MyiamPass!123", b64_der)
    decrypted = private_key.decrypt(base64.b64decode(encrypted_b64), padding.PKCS1v15())
    assert decrypted.decode("utf-8") == "MyiamPass!123"


def test_iam_login_flow(monkeypatch, test_env):
    user = "alice"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    b64_der = "".join(
        line.strip() for line in public_pem.splitlines() if not line.startswith("-----")
    )
    monkeypatch.setattr(tongji_oj_client, "IAM_RSA_PUBLIC_KEY_B64", b64_der)

    iam_page_html = """
    <html>
    <script>$("#spAuthChainCode1").val('4c1eb805953c4f829ef0070c26dc29b0');</script>
    <form id="loginForm" action="/idp/authcenter/AuthnEngine">
      <input id="spAuthChainCode" name="spAuthChainCode" value="4c1eb805953c4f829ef0070c26dc29b0" />
      <input id="authnLcKey" name="authnLcKey" value="lckey_999" />
    </form>
    </html>
    """

    class FakeJar(dict):
        def get_dict(self):
            return dict(self)

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.cookies = FakeJar({"shjsession": "iam_logged_in_cookie"})

        def get(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "Unified_Certification" in url:
                resp.url = "https://iam.tongji.edu.cn/idp/authcenter/ActionAuthChain?entityId=SYS20240302&authnLcKey=lckey_999"
                resp.text = iam_page_html
            else:
                resp.url = "https://oj.tongji.edu.cn/index.php/dashboard#1"
                resp.text = SAMPLE_ASSIGNMENTS_HTML
            return resp

        def post(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "displayVerificationCode" in url:
                resp.text = "false"
                resp.url = url
            elif "ActionAuthChain" in url:
                resp.json.return_value = {"loginFailed": "false", "j_username": "2559999"}
                resp.text = '{"loginFailed":"false","j_username":"2559999"}'
                resp.url = url
            elif "AuthnEngine" in url:
                resp.url = "https://oj.tongji.edu.cn/index.php/dashboard#1"
                resp.text = "<html><title>Dashboard - Tongji Online Judge</title></html>"
            return resp

    monkeypatch.setattr(tongji_oj_client.requests, "Session", FakeSession)

    res = tongji_oj_client.iam_login(user, "2559999", "secret_iam_pass")
    assert res["ok"] is True
    assert tongji_oj_client.has_token(user)
    assert tongji_oj_client.load_credentials(user)["login_mode"] == "iam"


def test_state_actions(test_env):
    user = "alice"
    assert tongji_oj_client.load_state(user) == {
        "hidden": [], "highlighted": [], "deleted": [], "completed": [], "overrides": {}
    }

    tongji_oj_client.update_state(user, "hide", "tjoj_590")
    assert "tjoj_590" in tongji_oj_client.load_state(user)["hidden"]

    tongji_oj_client.update_state(user, "complete", "tjoj_590")
    assert "tjoj_590" in tongji_oj_client.load_state(user)["completed"]

    tongji_oj_client.update_override(user, "tjoj_590", patch={"title": "线性表练习", "due_ts": "2026-10-09T23:59:59+08:00"})
    state = tongji_oj_client.load_state(user)
    assert state["overrides"]["tjoj_590"]["title"] == "线性表练习"


def test_api_tongjioj_routes(client_with_user, monkeypatch, test_env):
    monkeypatch.setattr(dashboard_app, "has_tjoj_credentials", lambda username: True)
    monkeypatch.setattr(
        tongji_oj_client,
        "get_saved_courses",
        lambda username: [{"id": "45", "name": "2026秋数据结构与算法设计（刘春梅）"}],
    )

    resp = client_with_user.get("/api/tongjioj/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["has_token"] is True
    assert data["courses"][0]["id"] == "45"

    monkeypatch.setattr(dashboard_app, "tjoj_iam_login", lambda username, sid, pwd: {"ok": True})
    resp_iam = client_with_user.post(
        "/api/tongjioj/login-iam",
        json={"student_id": "2559999", "password": "pwd"},
        headers=client_with_user.csrf_headers,
    )
    assert resp_iam.status_code == 200
    assert resp_iam.get_json()["ok"] is True

    monkeypatch.setattr(dashboard_app, "tjoj_local_login", lambda username, acc, pwd: {"ok": True})
    resp_local = client_with_user.post(
        "/api/tongjioj/login-local",
        json={"account": "ojuser", "password": "pwd"},
        headers=client_with_user.csrf_headers,
    )
    assert resp_local.status_code == 200
    assert resp_local.get_json()["ok"] is True


def test_api_clear_platform_data_override_and_agent_complete(client_with_user, test_env):
    user = "testuser"
    user_p = test_env / "users" / user

    tongji_oj_client.save_credentials(user, "2559999", "pwd", login_mode="iam")
    write_json_file(
        user_p / "tongjioj_cache.json",
        {"items": [{"id": "tjoj_590", "title": "HW1线性表", "due_ts": "2026-10-08T23:59:59+08:00"}]},
    )
    write_json_file(
        user_p / "tongjioj_state.json",
        {"hidden": [], "highlighted": [], "deleted": [], "completed": [], "overrides": {}},
    )

    # Agent complete
    ok = dashboard_app._complete_agent_todo(user, "tjoj_590", source="tongjioj")
    assert ok is True
    assert "tjoj_590" in tongji_oj_client.load_state(user)["completed"]

    # Override
    resp = client_with_user.post(
        "/api/platform/tongjioj/override",
        json={"id": "tjoj_590", "title": "Renamed OJ Task"},
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    assert tongji_oj_client.load_state(user)["overrides"]["tjoj_590"]["title"] == "Renamed OJ Task"

    # Clear platform data
    resp = client_with_user.delete(
        "/api/platform/tongjioj/data",
        headers=client_with_user.csrf_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert not tongji_oj_client.has_token(user)
    assert not (user_p / "tongjioj_cache.json").exists()


def test_iam_xml_response_and_second_auth_flow(monkeypatch, test_env):
    user = "alice"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    b64_der = "".join(
        line.strip() for line in public_pem.splitlines() if not line.startswith("-----")
    )
    monkeypatch.setattr(tongji_oj_client, "IAM_RSA_PUBLIC_KEY_B64", b64_der)

    iam_page_html = """
    <html>
    <script>
      $("#spAuthChainCode1").val('4c1eb805953c4f829ef0070c26dc29b0');
      $("#spAuthChainCode24").val('81b76f3ebdc34fc4bb4dcffdf319cad7');
    </script>
    <form id="loginForm" action="/idp/authcenter/AuthnEngine">
      <input id="spAuthChainCode" name="spAuthChainCode" value="4c1eb805953c4f829ef0070c26dc29b0" />
      <input id="authnLcKey" name="authnLcKey" value="lckey_second_auth" />
    </form>
    </html>
    """

    class FakeJar(dict):
        def get_dict(self):
            return dict(self)

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.cookies = FakeJar({"shjsession": "iam_second_auth_cookie"})

        def get(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "Unified_Certification" in url:
                resp.url = "https://iam.tongji.edu.cn/idp/authcenter/ActionAuthChain?entityId=SYS20240302&authnLcKey=lckey_second_auth"
                resp.text = iam_page_html
            else:
                resp.url = "https://oj.tongji.edu.cn/index.php/dashboard#1"
                resp.text = SAMPLE_ASSIGNMENTS_HTML
            return resp

        def post(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.url = url
            data = kwargs.get("data") or {}
            if "displayVerificationCode" in url:
                resp.text = "false"
            elif "sendCheckCode.do" in url:
                assert kwargs.get("headers", {}).get("Accept") == tongji_oj_client.IAM_AJAX_ACCEPT
                resp.json.return_value = {"message": "I18NMessage.sendSMSCheckCodeSuccessmsg", "validTime": "3"}
                resp.text = '{"message":"I18NMessage.sendSMSCheckCodeSuccessmsg","validTime":"3"}'
            elif "ActionAuthChain" in url:
                assert kwargs.get("headers", {}).get("Accept") == tongji_oj_client.IAM_AJAX_ACCEPT
                if data.get("popViewException") == "Pop2":
                    assert data.get("sms_checkcode") == "654321"
                    assert data.get("spAuthChainCode") == "81b76f3ebdc34fc4bb4dcffdf319cad7"
                    resp.json.return_value = {"loginFailed": "false"}
                    resp.text = '{"loginFailed":"false"}'
                else:
                    # Simulate XML <JSONObject> response for unfamiliar device secondary auth
                    resp.json.side_effect = ValueError("No JSON")
                    resp.text = (
                        "<JSONObject>"
                        "<loginFailed>true</loginFailed>"
                        "<view>biometrics</view>"
                        "<authList>sms</authList>"
                        "<show_username>2559999</show_username>"
                        "<mobile>138****1234</mobile>"
                        "<currentAuChainCodeEx>81b76f3ebdc34fc4bb4dcffdf319cad7</currentAuChainCodeEx>"
                        "</JSONObject>"
                    )
            elif "AuthnEngine" in url:
                resp.url = "https://oj.tongji.edu.cn/index.php/dashboard#1"
                resp.text = "<html><title>Dashboard - Tongji Online Judge</title></html>"
            return resp

    monkeypatch.setattr(tongji_oj_client.requests, "Session", FakeSession)

    # Step 1: Primary IAM login triggers unfamiliar-device secondary verification
    res1 = tongji_oj_client.iam_login(user, "2559999", "secret_iam_pass")
    assert res1["ok"] is False
    assert res1["need_second_auth"] is True
    assert res1["mobile"] == "138****1234"
    assert res1["auth_methods"] == [{"type": "sms", "label": "手机短信 (138****1234)"}]

    # Step 2: Send SMS code
    res_send = tongji_oj_client.iam_send_second_auth_code(user, auth_type="sms")
    assert res_send["ok"] is True

    # Step 3: Verify SMS code and complete OAuth2 login to oj.tongji.edu.cn
    res_verify = tongji_oj_client.iam_verify_second_auth_code(user, code="654321", auth_type="sms")
    assert res_verify["ok"] is True
    assert tongji_oj_client.has_token(user)
    assert tongji_oj_client.load_credentials(user) == {
        "username": "2559999",
        "password": "secret_iam_pass",
        "login_mode": "iam",
    }


def test_tongjioj_frontend_login_entries():
    views_path = Path(__file__).parents[1] / "frontend" / "templates" / "dashboard" / "_placeholder_views.html"
    index_path = Path(__file__).parents[1] / "frontend" / "templates" / "index.html"
    views_html = views_path.read_text(encoding="utf-8")
    index_html = index_path.read_text(encoding="utf-8")

    assert 'data-od-id="connection-platform-tongjioj"' in views_html
    assert "同济OJ" in views_html
    assert 'id="tjoj-setup-inline" class="connection-stack"' in views_html
    assert 'id="tjoj-student-id-inline"' in views_html
    assert 'id="tjoj-iam-password-inline"' in views_html
    assert 'id="tjoj-second-auth-box-inline"' in views_html
    assert 'data-od-id="tongjioj-iam-login"' in views_html
    assert 'data-od-id="tongjioj-iam-send-code"' in views_html
    assert 'data-od-id="tongjioj-iam-verify-code"' in views_html
    assert 'data-od-id="tongjioj-local-login"' in views_html
    assert "loadTongjiojStatusInline" in index_html
    assert "sendTongjiojSecondAuthCodeInline" in index_html
    assert "verifyTongjiojSecondAuthCodeInline" in index_html
    assert "fetchTongjiojTodos" in index_html

