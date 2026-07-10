import json

import pytest

import app as dashboard_app
import apple_calendar
import user_paths
import zhihuishu_store


@pytest.fixture
def calendar_client(tmp_path, monkeypatch):
    def resolve_user_dir(username):
        path = tmp_path / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", resolve_user_dir)
    monkeypatch.setattr(apple_calendar, "DATA_DIR", tmp_path)
    monkeypatch.setattr(apple_calendar, "user_dir", resolve_user_dir)
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client, resolve_user_dir


def test_calendar_subscription_reads_only_active_cached_tasks(calendar_client, monkeypatch):
    client, user_dir = calendar_client
    user_dir("alice").joinpath("custom_todos.json").write_text(
        json.dumps([
            {"id": 1, "text": "Custom due date", "due_date": "2099-07-11", "done": False},
            {"id": 2, "text": "Completed custom", "due_date": "2099-07-11", "done": True},
        ]),
        encoding="utf-8",
    )
    user_dir("alice").joinpath("canvas_cache.json").write_text(
        json.dumps([
            {"id": 11, "title": "Canvas visible", "due_ts": "2099-07-12T09:00:00+08:00"},
            {"id": 12, "title": "Canvas hidden", "due_ts": "2099-07-12T09:00:00+08:00"},
        ]),
        encoding="utf-8",
    )
    user_dir("alice").joinpath("canvas_state.json").write_text('{"hidden": [12], "highlighted": [], "deleted": []}', encoding="utf-8")
    user_dir("alice").joinpath("haoke_cache.json").write_text(
        json.dumps([{"id": 21, "title": "Haoke visible", "due_ts": "2099-07-12T10:00:00+08:00"}]),
        encoding="utf-8",
    )
    user_dir("alice").joinpath("zhixuemeng_cache.json").write_text(
        json.dumps({"items": [{"id": "zxm-31", "title": "Zxm visible", "due_ts": "2099-07-12T11:00:00+08:00"}]}),
        encoding="utf-8",
    )
    zhihuishu_store.save_cache("alice", [{"id": "zhs-41", "title": "Zhs visible", "due_ts": "2099-07-12T12:00:00+08:00"}])

    monkeypatch.setattr(dashboard_app, "fetch_canvas_planner", lambda username: pytest.fail("calendar subscription must not fetch Canvas"))
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: pytest.fail("calendar subscription must not fetch 好课"))
    monkeypatch.setattr(dashboard_app, "fetch_zxm_assignments", lambda username: pytest.fail("calendar subscription must not fetch 智学盟"))

    created = client.post("/api/apple-calendar/subscription", headers=client.csrf_headers)

    assert created.status_code == 200
    path = created.get_json()["path"]

    with dashboard_app.app.test_client() as anonymous_client:
        response = anonymous_client.get(path)

    assert response.status_code == 200
    assert response.content_type == "text/calendar; charset=utf-8"
    body = response.get_data(as_text=True)
    for title in ("Custom due date", "Canvas visible", "Haoke visible", "Zxm visible", "Zhs visible"):
        assert title in body
    assert "DTSTART;VALUE=DATE:20990711" in body
    assert "Completed custom" not in body
    assert "Canvas hidden" not in body
    assert "alice" not in body


def test_calendar_subscription_token_is_revocable(calendar_client):
    client, _ = calendar_client

    created = client.post("/api/apple-calendar/subscription", headers=client.csrf_headers)
    assert created.status_code == 200
    path = created.get_json()["path"]

    revoked = client.delete("/api/apple-calendar/subscription", headers=client.csrf_headers)
    assert revoked.status_code == 200
    assert revoked.get_json() == {"ok": True}

    with dashboard_app.app.test_client() as anonymous_client:
        assert anonymous_client.get(path).status_code == 404
        assert anonymous_client.get("/calendar/not-a-token.ics").status_code == 404
