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

    assert resp.status_code == 503
    body = resp.get_json()
    worker = body["checks"]["zhihuishu_worker"]
    assert worker["ok"] is False
    assert worker["error_count"] == 1
