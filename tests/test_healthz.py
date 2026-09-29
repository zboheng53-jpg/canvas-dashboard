import pytest

import app as dashboard_app
import zhihuishu_store


@pytest.fixture
def health_client(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        yield client


def test_healthz_is_public_and_uses_only_local_checks(health_client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app.zhihuishu_worker,
        "run_scheduled_cycle",
        lambda *args, **kwargs: pytest.fail("healthz must not trigger worker refresh"),
    )
    monkeypatch.setattr(
        dashboard_app.zhihuishu_login_sessions,
        "create_session",
        lambda *args, **kwargs: pytest.fail("healthz must not create login sessions"),
    )

    resp = health_client.get("/healthz")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["checks"]["app"]["ok"] is True
    assert body["checks"]["data_writable"]["ok"] is True
    assert body["checks"]["zhihuishu_worker"]["ok"] is True
    assert body["checks"]["zhihuishu_worker"]["user_count"] == 0


def test_healthz_returns_503_when_data_directory_is_not_writable(tmp_path, monkeypatch):
    data_file = tmp_path / "not-a-directory"
    data_file.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "DATA_DIR", data_file)
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", data_file)
    dashboard_app.app.config.update(TESTING=True)

    with dashboard_app.app.test_client() as client:
        resp = client.get("/healthz")

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["ok"] is False
    assert body["checks"]["app"]["ok"] is True
    assert body["checks"]["data_writable"]["ok"] is False


def test_healthz_reports_local_worker_error_status(health_client):
    user_dir = zhihuishu_store.DATA_DIR / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "zhihuishu_status.json").write_text(
        '{"worker": "error", "last_error": "login expired"}',
        encoding="utf-8",
    )

    resp = health_client.get("/healthz")

    # Worker error must degrade status without failing whole-site 503
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["status"] == "degraded"
    worker = body["checks"]["zhihuishu_worker"]
    assert worker["ok"] is False
    assert worker["error_count"] == 1


def test_healthz_reports_worker_success_refresh_times(health_client, monkeypatch):
    monkeypatch.setattr(dashboard_app.time, "time", lambda: 10_000.0)
    for username, last_success in (("alice", 9_900.0), ("bob", 9_800.0)):
        user_dir = zhihuishu_store.DATA_DIR / "users" / username
        user_dir.mkdir(parents=True)
        (user_dir / "zhihuishu_status.json").write_text(
            f'{{"worker": "running", "last_success_at": {last_success}}}',
            encoding="utf-8",
        )

    resp = health_client.get("/healthz")

    assert resp.status_code == 200
    worker = resp.get_json()["checks"]["zhihuishu_worker"]
    assert worker["last_success_at"] == 9_900.0
    assert worker["oldest_last_success_at"] == 9_800.0
    assert worker["last_success_age_seconds"] == 100
    assert worker["last_success_count"] == 2


def test_livez_and_readyz_endpoints(health_client, tmp_path, monkeypatch):
    # /livez is public and alive
    live_resp = health_client.get("/livez")
    assert live_resp.status_code == 200
    assert live_resp.get_json() == {"ok": True, "status": "alive"}

    # /readyz is ready when storage is accessible
    ready_resp = health_client.get("/readyz")
    assert ready_resp.status_code == 200
    assert ready_resp.get_json()["ok"] is True
    assert ready_resp.get_json()["status"] == "ready"

    # Diagnostics endpoint
    diag_resp = health_client.get("/api/diagnostics/workers")
    assert diag_resp.status_code == 401
    with health_client.session_transaction() as session:
        session['username'] = 'alice'
    diag_resp = health_client.get("/api/diagnostics/workers")
    assert diag_resp.status_code == 200
    assert diag_resp.get_json()["ok"] is True


def test_readyz_fails_closed_on_corrupt_data(health_client, tmp_path, monkeypatch):
    # Simulate corrupted users.json
    corrupt_users = dashboard_app.DATA_DIR / "users.json"
    corrupt_users.write_text("{corrupt:json:not:valid", encoding="utf-8")

    ready_resp = health_client.get("/readyz")
    assert ready_resp.status_code == 503
    assert ready_resp.get_json()["ok"] is False

    health_resp = health_client.get("/healthz")
    assert health_resp.status_code == 503
    assert health_resp.get_json()["ok"] is False
