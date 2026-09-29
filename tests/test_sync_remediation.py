from operation_helpers import wait_weather
import auth
import json
import os
import subprocess
import sys
import time
import threading
from pathlib import Path
import pytest

import settings
import zhihuishu_store
import zhihuishu_worker
import zhihuishu_browser
import login_capacity
import zhihuishu_login_sessions
import tongji_login_sessions
import http_sync
import platform_sync
import canvas_auth
import haoke_client
import app as dashboard_app


def test_zhihuishu_response_validation():
    """Valid empty responses return [], whereas invalid or error responses return None."""
    class FakeResponse:
        def __init__(self, status=200, payload=None, throws=False):
            self.status = status
            self._payload = payload
            self._throws = throws

        def json(self):
            if self._throws:
                raise ValueError("Bad JSON")
            return self._payload

    # Valid empty data
    resp_empty = FakeResponse(status=200, payload={"code": 200, "data": []})
    assert zhihuishu_browser._task_list_response_items(resp_empty) == []

    # Valid list with items
    resp_items = FakeResponse(status=200, payload={"code": 200, "data": [{"id": 101}]})
    assert zhihuishu_browser._task_list_response_items(resp_items) == [{"id": 101}]

    # Code 0 is also success in Zhihuishu
    resp_code_0 = FakeResponse(status=200, payload={"code": 0, "data": []})
    assert zhihuishu_browser._task_list_response_items(resp_code_0) == []

    # Error code 500 -> None (must not be treated as empty)
    resp_err = FakeResponse(status=200, payload={"code": 500, "message": "Server error", "data": None})
    assert zhihuishu_browser._task_list_response_items(resp_err) is None

    # HTTP 500 status -> None
    resp_http_500 = FakeResponse(status=500, payload={"data": []})
    assert zhihuishu_browser._task_list_response_items(resp_http_500) is None

    # JSON parse error -> None
    resp_bad_json = FakeResponse(status=200, throws=True)
    assert zhihuishu_browser._task_list_response_items(resp_bad_json) is None

    # Data is not a list -> None
    resp_non_list = FakeResponse(status=200, payload={"code": 200, "data": "unexpected string"})
    assert zhihuishu_browser._task_list_response_items(resp_non_list) is None


def test_zhihuishu_complete_failure_preserves_old_cache(tmp_path, monkeypatch):
    """When Zhihuishu fetch completely fails, old cache must never be overwritten."""
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(platform_sync, "user_dir", lambda username: tmp_path / "users" / username)

    # Setup connected state and old cache
    platform_sync.mark_connected("alice", "zhihuishu")
    old_items = [{"id": "zhs_old_1", "course": "Advanced Math", "title": "Homework 1"}]
    zhihuishu_store.save_cache("alice", old_items, fetched_at=1000.0)
    zhihuishu_store.save_status("alice", {"session": "active", "last_fetch_at": 1000.0})

    class FailingBrowser:
        @staticmethod
        def check_session(username):
            return True

        @staticmethod
        def keepalive(username):
            return True

        @staticmethod
        def fetch_assignments(username):
            # Simulated full failure across all courses
            return zhihuishu_browser.AssignmentFetchResult(
                [],
                ok=False,
                partial=False,
                failed_courses=["Advanced Math"],
            )

    monkeypatch.setattr(zhihuishu_worker, "zhihuishu_browser", FailingBrowser, raising=False)

    ok = zhihuishu_worker.run_scheduled_cycle("alice", now=5000.0, force_fetch=True)
    assert ok is False

    # Cache MUST still be the old items with original fetched_at
    cache = zhihuishu_store.load_cache("alice")
    assert cache["items"] == old_items
    assert cache["fetched_at"] == 1000.0

    # Status must reflect error
    status = zhihuishu_store.load_status("alice")
    assert status["worker"] == "error"
    assert "抓取失败" in status["last_error"]

    # Platform sync must report failure while preserving has_cache=True
    sync_entry = platform_sync.get("alice", "zhihuishu")
    assert sync_entry["connection_state"] == "connected"
    assert sync_entry["error_code"] == "fetch_failed"


def test_zhihuishu_partial_failure_merges_failed_courses_from_old_cache(tmp_path, monkeypatch):
    """When some courses fail, old items for the failed courses are preserved and merged."""
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(platform_sync, "user_dir", lambda username: tmp_path / "users" / username)

    old_items = [
        {"id": "zhs_math_old", "course": "Math", "title": "Old Math Task"},
        {"id": "zhs_physics_old", "course": "Physics", "title": "Old Physics Task"},
    ]
    zhihuishu_store.save_cache("alice", old_items, fetched_at=1000.0)
    zhihuishu_store.save_status("alice", {"session": "active", "last_fetch_at": 1000.0})

    # Math succeeded with new task; Physics failed
    fresh_math_item = {"id": "zhs_math_new", "course": "Math", "title": "New Math Task"}

    class PartialBrowser:
        @staticmethod
        def check_session(username):
            return True

        @staticmethod
        def keepalive(username):
            return True

        @staticmethod
        def fetch_assignments(username):
            return zhihuishu_browser.AssignmentFetchResult(
                [fresh_math_item],
                ok=True,
                partial=True,
                succeeded_courses=["Math"],
                failed_courses=["Physics"],
            )

    monkeypatch.setattr(zhihuishu_worker, "zhihuishu_browser", PartialBrowser, raising=False)

    ok = zhihuishu_worker.run_scheduled_cycle("alice", now=5000.0, force_fetch=True)
    assert ok is False  # Partial success remains a retryable degraded result.

    cache = zhihuishu_store.load_cache("alice")
    saved_ids = {it["id"] for it in cache["items"]}

    # New Math task is saved, old Math task is replaced
    assert "zhs_math_new" in saved_ids
    assert "zhs_math_old" not in saved_ids
    # Old Physics task is preserved because Physics failed!
    assert "zhs_physics_old" in saved_ids

    status = zhihuishu_store.load_status("alice")
    assert status["partial_fetch"] is True
    assert status["failed_courses"] == ["Physics"]
    assert status['last_fetch_at'] == 1000.0
    assert platform_sync.get('alice', 'zhihuishu')['error_code'] == 'partial_fetch'


def test_foreign_chromium_lock_not_stale():
    """Locks created by containers or other hostnames must not be marked stale."""
    assert not zhihuishu_browser._profile_lock_is_stale(
        "container-abc-1234",
        current_host="host-machine",
        pid_is_running=lambda pid: False,
    )


def test_shared_browser_quota_and_profile_lock(tmp_path, monkeypatch):
    """noVNC startup and worker share settings.LOGIN_MAX_SESSIONS, and profile lock provides mutual exclusion."""
    monkeypatch.setattr(settings, "LOGIN_MAX_SESSIONS", 1)

    # 1. Profile lock mutual exclusion across processes
    with login_capacity.account_profile_lock(tmp_path, "alice", timeout=2.0):
        # Alice cannot be acquired by another process concurrently
        data_dir_str = str(tmp_path).replace("\\", "\\\\")
        script = (
            f"from pathlib import Path\n"
            f"import login_capacity\n"
            f"try:\n"
            f"    with login_capacity.account_profile_lock(Path(r'{data_dir_str}'), 'alice', timeout=0.2):\n"
            f"        print('acquired')\n"
            f"except TimeoutError:\n"
            f"    print('timeout')\n"
        )
        res = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
        assert res.stdout.strip() == "timeout"

        # Bob can acquire concurrently in another process (different accounts)
        script_bob = (
            f"from pathlib import Path\n"
            f"import login_capacity\n"
            f"try:\n"
            f"    with login_capacity.account_profile_lock(Path(r'{data_dir_str}'), 'bob', timeout=0.2):\n"
            f"        print('acquired')\n"
            f"except TimeoutError:\n"
            f"    print('timeout')\n"
        )
        res_bob = subprocess.run([sys.executable, "-c", script_bob], capture_output=True, text=True, check=True)
        assert res_bob.stdout.strip() == "acquired"

    # 2. Shared browser quota
    session_file = tmp_path / "users" / "alice" / "zhihuishu_login_session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps({"port": 6080}), encoding="utf-8")

    with login_capacity.startup_slot(tmp_path, session_file):
        # When noVNC startup slot is held, worker browser slot must be rejected (quota = 1)
        with pytest.raises(login_capacity.LoginCapacityError):
            with login_capacity.worker_browser_slot(tmp_path, username="alice"):
                pass

    # Once noVNC session ends (session file removed), worker browser slot can acquire
    session_file.unlink()
    with login_capacity.worker_browser_slot(tmp_path, username="alice"):
        assert True


def test_login_session_starting_grace_period(tmp_path, monkeypatch):
    """Sessions in 'starting' state within grace period are not killed as expired or orphaned."""
    monkeypatch.setattr(zhihuishu_login_sessions, "DATA_DIR", tmp_path)
    stopped_containers = []
    monkeypatch.setattr(zhihuishu_login_sessions, "_stop_container", lambda name: stopped_containers.append(name))
    monkeypatch.setattr(zhihuishu_login_sessions, "_list_login_containers", lambda: ["canvas-zhs-login-token123"])

    session_file = tmp_path / "users" / "alice" / "zhihuishu_login_session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    now = 1000.0
    # Starting session created 15s ago (grace period is 60s)
    session_data = {
        "username": "alice",
        "token": "token123",
        "container_name": "canvas-zhs-login-token123",
        "status": "starting",
        "created_at": now - 15.0,
        "expires_at": now - 5.0,  # even if expires_at is past, grace period protects it
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    # cleanup_expired_sessions must not remove it
    removed = zhihuishu_login_sessions.cleanup_expired_sessions(now=now)
    assert removed == 0
    assert session_file.exists()

    # cleanup_orphaned_containers must not treat it as orphan
    orphans = zhihuishu_login_sessions.cleanup_orphaned_containers(now=now)
    assert orphans == 0
    assert stopped_containers == []

    # When grace period has passed (70s > 60s)
    removed_later = zhihuishu_login_sessions.cleanup_expired_sessions(now=now + 60.0)
    assert removed_later == 1
    assert not session_file.exists()
    assert "canvas-zhs-login-token123" in stopped_containers


def test_http_sync_deduplication_and_bounded_executor(isolated_data):
    auth.register("alice", "password1")
    """HTTP sync coalesces concurrent identical requests and limits concurrency."""
    call_counts = {"count": 0}
    event = threading.Event()

    def slow_task():
        call_counts["count"] += 1
        event.wait(timeout=2.0)
        return "result"

    # Submit twice for the same user and platform
    t1 = http_sync.submit_http_sync("alice", "canvas", slow_task)
    t2 = http_sync.submit_http_sync("alice", "canvas", slow_task)

    assert t1 is True
    assert t2 is False  # Already queued/running
    assert http_sync.is_refreshing("alice", "canvas") is True

    event.set()
    # Wait for completion
    deadline = time.time() + 2.0
    while http_sync.is_refreshing("alice", "canvas") and time.time() < deadline:
        time.sleep(0.05)

    assert not http_sync.is_refreshing("alice", "canvas")
    assert call_counts["count"] == 1


def test_http_sync_aborts_writeback_on_identity_change(tmp_path, monkeypatch):
    """If user identity changes or user disconnects during sync, results are not written back."""
    monkeypatch.setattr(canvas_auth, "user_dir", lambda username: tmp_path / "users" / username)
    monkeypatch.setattr(platform_sync, "user_dir", lambda username: tmp_path / "users" / username)
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    feed_url = "https://canvas.example.edu/feed.ics"
    (user_dir / "config.json").write_text(json.dumps({"calendar_feed_url": feed_url}), encoding="utf-8")

    cache_file = user_dir / "canvas_cache.json"
    cache_file.write_text(json.dumps([{"id": "initial_cached_item"}]), encoding="utf-8")

    # Initial identity
    current_identity = {"identity": "ver-1"}
    monkeypatch.setattr(http_sync, "get_account_identity", lambda username: current_identity["identity"])

    called = []
    class Response:
        status_code = 200
        text = "ignored"
    def fetch(*args, **kwargs):
        called.append(True)
        current_identity["identity"] = "ver-2"
        return Response()
    monkeypatch.setattr(canvas_auth, "validate_feed_url", lambda _: (True, None))
    monkeypatch.setattr(canvas_auth.requests, "get", fetch)
    monkeypatch.setattr(canvas_auth, "_parse_ical", lambda _: [{"id": "canvas:assignment:42"}])
    # Run the background refresh
    canvas_auth._run_background_refresh("alice")

    # Writeback must NOT occur because identity changed mid-flight!
    # Cache content must remain the initial cached item!
    assert called == [True]
    cached_content = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cached_content == [{"id": "initial_cached_item"}]


def test_weather_shared_cache_and_coalescing(tmp_path, monkeypatch):
    """Weather requests for the same campus share cache and coalesce in-flight requests."""
    fetch_calls = {"count": 0}

    class FakeResponse:
        def json(self):
            return {
                "current": {
                    "temperature_2m": 22.5,
                    "relative_humidity_2m": 60,
                    "weather_code": 0,
                }
            }

    def fake_requests_get(url, timeout=5):
        fetch_calls["count"] += 1
        time.sleep(0.1)
        return FakeResponse()

    monkeypatch.setattr(dashboard_app.requests, "get", fake_requests_get)
    dashboard_app._weather_cache.clear()

    # User directory and session setup
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", lambda username: user_dir)
    dashboard_app.app.config.update(TESTING=True)

    client = dashboard_app.app.test_client()
    with client.session_transaction() as sess:
        sess["username"] = "alice"

    # Concurrent requests for the same campus
    res1 = []
    res2 = []

    def req1():
        with dashboard_app.app.test_client() as c:
            with c.session_transaction() as s:
                s["username"] = "alice"
            r = c.get("/api/weather?campus=jiading")
            res1.append(r.get_json())

    def req2():
        with dashboard_app.app.test_client() as c:
            with c.session_transaction() as s:
                s["username"] = "alice"
            r = c.get("/api/weather?campus=jiading")
            res2.append(r.get_json())

    th1 = threading.Thread(target=req1)
    th2 = threading.Thread(target=req2)
    th1.start()
    th2.start()
    th1.join()
    th2.join()

    assert res1[0]["pending"] is True
    assert res2[0]["pending"] is True
    assert wait_weather(client, "jiading").json["temperature"] == 22.5
    # Upstream was called only ONCE due to coalescing!
    assert fetch_calls["count"] == 1

    # Third call immediately after uses cache without upstream call
    r3 = client.get("/api/weather?campus=jiading")
    assert r3.get_json()["ok"] is True
    assert fetch_calls["count"] == 1
