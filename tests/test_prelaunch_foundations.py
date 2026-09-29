from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
import requests

import pytest

import app as dashboard
import auth
import http_sync
import platform_http
import schedule_store
import system_monitor
from storage import read_json_file, write_json_file


def client_for(username="alice"):
    client = dashboard.app.test_client()
    with client.session_transaction() as session:
        session.update(username=username, account_id=auth.session_identity(username)[0],
                       session_version=1, _csrf_token="test")
    return client


def test_same_account_local_get_can_run_while_another_get_is_blocked(isolated_data, monkeypatch):
    auth.register("alice", "password1")
    monkeypatch.setitem(dashboard.app.config, "TESTING", True)
    started, release = threading.Event(), threading.Event()
    original = schedule_store.load_courses
    def blocked(username):
        started.set()
        assert release.wait(5)
        return original(username)
    monkeypatch.setattr(schedule_store, "load_courses", blocked)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(lambda: client_for().get("/api/schedule"))
        assert started.wait(2)
        try:
            before = time.monotonic()
            assert client_for().get("/api/projects").status_code == 200
            assert time.monotonic() - before < 1
        finally:
            release.set()
        assert first.result(timeout=2).status_code == 200


def test_old_job_cannot_write_into_reregistered_same_username(isolated_data):
    auth.register("alice", "password1")
    started, release, done = threading.Event(), threading.Event(), threading.Event()
    path = isolated_data / "users/alice/custom_todos.json"
    def old_job():
        started.set()
        assert release.wait(5)
        write_json_file(path, [{"title": "old identity"}])
    assert http_sync.submit_http_sync("alice", "canvas", old_job, on_finished=done.set)
    assert started.wait(2)
    try:
        assert auth.delete_account("alice", "password1", auth.DELETE_CONFIRMATION, before_delete=lambda: None)[0]
        assert auth.register("alice", "password2")[0]
        write_json_file(path, [{"title": "new identity"}])
    finally:
        release.set()
        assert done.wait(3)
    assert read_json_file(path, []) == [{"title": "new identity"}]


@pytest.mark.parametrize("platform", ["zhixuemeng", "ketangpai"])
def test_token_platform_stale_reads_and_config_never_wait_for_upstream(isolated_data, monkeypatch, platform):
    auth.register("alice", "password1")
    client = platform_http._client(platform)
    monkeypatch.setattr(client, "has_token", lambda username: True)
    monkeypatch.setattr(dashboard, "has_zxm_token" if platform == "zhixuemeng" else "has_ktp_token", lambda _: True)
    queued = []
    monkeypatch.setattr(http_sync, "submit_http_sync", lambda username, p, *args, **kwargs: queued.append(p) or True)
    monkeypatch.setattr(client, "fetch_assignments", lambda *a, **kw: pytest.fail("GET fetched upstream"))
    monkeypatch.setattr(client, "fetch_courses", lambda *a, **kw: pytest.fail("config fetched upstream"))
    write_json_file(isolated_data / f"users/alice/{platform}_cache.json",
                    {"items": [{"id": "old", "title": "可信缓存"}], "courses": [{"id": "c"}], "_ts": 1})
    response = client_for().get(f"/api/{platform}/todos")
    assert response.status_code == 200
    assert response.json["data"][0]["id"] == "old"
    assert client_for().get(f"/api/{platform}/config").json["courses"] == [{"id": "c"}]
    assert queued == [platform, platform]
    assert client_for().get(f"/api/{platform}/todos?cache_only=1").status_code == 200
    assert queued == [platform, platform]


def test_login_returns_202_and_local_requests_remain_responsive(isolated_data, monkeypatch):
    auth.register("alice", "password1")
    monkeypatch.setitem(dashboard.app.config, "TESTING", True)
    started, release = threading.Event(), threading.Event()
    def login(*args):
        started.set()
        assert release.wait(5)
        return {"ok": True}
    monkeypatch.setattr(dashboard, "ktp_password_login", login)
    client = client_for()
    result = client.post("/api/ketangpai/login-password", json={"account": "student", "password": "secret"},
                         headers={"X-CSRF-Token": "test"})
    assert result.status_code == 202
    assert started.wait(2)
    try:
        assert client.get("/api/projects").status_code == 200
        assert client.get(result.json["status_url"]).json["state"] == "running"
        auth.register("bobby", "password1")
        assert client_for("bobby").get(result.json["status_url"]).status_code == 404
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get(result.json["status_url"]).json
        if status["state"] == "done":
            assert status["result"] == {"ok": True}
            break
        time.sleep(0.01)
    else:
        pytest.fail("login did not finish")


def test_haoke_full_queue_does_not_report_nonexistent_refresh(isolated_data, monkeypatch):
    auth.register("alice", "password1")
    monkeypatch.setattr(dashboard, "has_haoke_credentials", lambda _: True)
    monkeypatch.setattr(dashboard, "get_haoke_cached_todos", lambda _: None)
    monkeypatch.setattr(dashboard, "start_haoke_background_refresh", lambda _: False)
    monkeypatch.setattr(dashboard, "is_haoke_refreshing", lambda _: False)
    response = client_for().get("/api/haoke/todos")
    assert response.status_code == 200 and response.json["data"] == []
    assert response.json["sync"]["refreshing"] is False


def test_shared_queue_caps_all_five_platforms_and_dedups_by_job_type(isolated_data, monkeypatch):
    auth.register("alice", "password1")
    monkeypatch.setattr(http_sync, "HTTP_SYNC_MAX_JOBS", 5)
    started = threading.Barrier(3)
    release = threading.Event()
    done = threading.Event()
    finished = []
    def blocked():
        started.wait(timeout=3)
        assert release.wait(5)
    def finish():
        finished.append(True)
        if len(finished) == 5:
            done.set()
    try:
        assert http_sync.submit_http_sync("alice", "canvas", blocked, on_finished=finish)
        assert http_sync.submit_http_sync("alice", "haoke", blocked, on_finished=finish)
        started.wait(timeout=3)
        for platform in ("zhixuemeng", "ketangpai", "tongjioj"):
            assert http_sync.submit_http_sync("alice", platform, lambda: None, on_finished=finish)
        status = http_sync.snapshot()
        assert status["running"] == 2 and status["queued"] == 3
        assert not http_sync.submit_http_sync("alice", "canvas", lambda: pytest.fail("duplicate"))
        assert not http_sync.submit_http_sync("alice", "canvas", lambda: pytest.fail("capacity"), job_type="login")
    finally:
        release.set()
        assert done.wait(3)


def test_linux_resource_sample_reports_actual_counters(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "meminfo").write_text("MemAvailable: 250000 kB\nSwapTotal: 100000 kB\nSwapFree: 75000 kB\n")
    (proc / "vmstat").write_text("pswpin 12\npswpout 30\noom_kill 1\n")
    (proc / "loadavg").write_text("0.25 0.50 0.75 1/100 123\n")
    monkeypatch.setattr(system_monitor.os, "sysconf", lambda _: 4096, raising=False)
    status = system_monitor.system_snapshot(tmp_path, proc)
    assert status["linux_counters_available"]
    assert status["mem_available_bytes"] == 250000 * 1024
    assert status["swap_used_bytes"] == 25000 * 1024
    assert status["swap_out_pages"] == 30 and status["oom_kills"] == 1
    assert status["load_average"] == [0.25, 0.5, 0.75]
    assert "memory_below_300_mib" in status["alerts"]


def test_nginx_limits_and_isolates_downstream_headers():
    for name in ("canvas-dashboard.nginx", "canvas-dashboard.https.nginx"):
        text = (Path(__file__).parents[1] / "deploy" / name).read_text(encoding="utf-8")
        assert "client_max_body_size 8m;" in text
        static = text.split("location ^~ /static/", 1)[1].split("\n    }", 1)[0]
        assert "alias /home/ubuntu/canvas-dashboard/current/frontend/assets/" in static
        assert "proxy_pass" not in static
        assert "max-age=31536000, immutable" in static
        assert "public, no-cache" in static
        for platform in ("zhs", "tji"):
            vnc = text.split('location ~ "^/' + platform + '-vnc/', 1)[1].split("\n    }", 1)[0]
            assert 'proxy_set_header Cookie "";' in vnc
            assert 'proxy_set_header Authorization "";' in vnc
        assert "http://127.0.0.1:8080" not in text and "http://127.0.0.1:5002" not in text


@pytest.mark.waitress(threads=2)
def test_queued_login_keeps_body_after_waitress_returns_202(live_app, isolated_data, monkeypatch):
    auth.register("queueduser", "password1")
    identity = auth.session_identity("queueduser")
    signer = dashboard.app.session_interface.get_signing_serializer(dashboard.app)
    client = requests.Session()
    client.cookies.set(dashboard.app.config["SESSION_COOKIE_NAME"], signer.dumps({
        "username": "queueduser", "account_id": identity[0], "session_version": identity[1], "_csrf_token": "test"}))
    started = threading.Barrier(3)
    release, finished = threading.Event(), threading.Event()
    def blocked():
        started.wait(timeout=5)
        assert release.wait(10)
    captured = []
    def login(username, account, password):
        captured.append((username, account, password))
        return {"ok": True}
    monkeypatch.setattr(dashboard, "ktp_password_login", login)
    try:
        assert http_sync.submit_http_sync("queueduser", "canvas", blocked)
        assert http_sync.submit_http_sync("queueduser", "haoke", blocked)
        started.wait(timeout=5)
        response = client.post(live_app + "/api/ketangpai/login-password", json={"account": "student", "password": "fake-secret"},
                               headers={"X-CSRF-Token": "test"}, timeout=5)
        assert response.status_code == 202
        assert client.get(live_app + "/api/projects", timeout=5).status_code == 200
        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = client.get(live_app + response.json()["status_url"], timeout=5).json()
            if result["state"] == "done":
                break
            finished.wait(.02)
        assert result["result_status"] == 200 and result["result"]["ok"]
        assert captured == [("queueduser", "student", "fake-secret")]
    finally:
        release.set()
        http_sync._executor.submit(lambda: None).result(timeout=5)
        client.close()
