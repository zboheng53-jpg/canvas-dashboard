from datetime import datetime, timedelta
from pathlib import Path

import pytest

import haoke_client


def _user_dir(root: Path):
    def resolve(username):
        path = root / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    return resolve


@pytest.fixture(autouse=True)
def clear_token_cache():
    haoke_client._token_cache.clear()
    if hasattr(haoke_client, "_refreshing_users"):
        haoke_client._refreshing_users.clear()
    yield
    haoke_client._token_cache.clear()
    if hasattr(haoke_client, "_refreshing_users"):
        haoke_client._refreshing_users.clear()


def test_parse_date_supports_timestamps_iso_and_common_formats():
    timestamp_ms = int(datetime(2099, 7, 10, 8, 30, tzinfo=haoke_client.CST).timestamp() * 1000)
    assert haoke_client._parse_date(timestamp_ms).isoformat() == "2099-07-10T08:30:00+08:00"
    assert haoke_client._parse_date("2099-07-10T01:00:00Z").isoformat() == "2099-07-10T09:00:00+08:00"
    assert haoke_client._parse_date("2099/07/10 08:30:00").isoformat() == "2099-07-10T08:30:00+08:00"
    assert haoke_client._parse_date("not-a-date") is None


def test_normalize_task_keeps_future_due_and_filters_expired_or_sentinel():
    future = haoke_client._normalize_task(
        {
            "taskId": 11,
            "taskName": "Future task",
            "taskType": 30,
            "endTime": "2099-07-10 08:30:00",
            "instanceId": "inst-1",
        },
        "Automation",
    )
    expired = haoke_client._normalize_task({"taskId": 12, "taskName": "Expired", "endTime": "2000-01-01"}, "Course")
    sentinel = haoke_client._normalize_task({"taskId": 13, "taskName": "No deadline", "endTime": "9999-01-01"}, "Course")

    assert future["id"] == 11
    assert future["title"] == "Future task"
    assert future["course"] == "Automation"
    assert future["due_str"] == "07-10 08:30"
    assert future["due_ts"] == "2099-07-10T08:30:00+08:00"
    assert future["url"].endswith("/student/course/inst-1/home?taskId=11")
    assert expired is None
    assert sentinel is None


def test_get_token_uses_per_user_cache_and_save_credentials_invalidates_only_that_user(tmp_path, monkeypatch):
    monkeypatch.setattr(haoke_client, "user_dir", _user_dir(tmp_path))
    monkeypatch.setattr(haoke_client, "_encrypt_password_local", lambda password: f"enc:{password}")
    future = datetime.now(haoke_client.CST) + timedelta(hours=1)
    haoke_client._token_cache.update(
        {
            "alice": {"token": "alice-token", "expires_at": future},
            "bob": {"token": "bob-token", "expires_at": future},
        }
    )

    assert haoke_client._get_token("alice") == "alice-token"

    haoke_client.save_credentials("alice", "alice_no", "new-password")

    assert "alice" not in haoke_client._token_cache
    assert haoke_client._token_cache["bob"]["token"] == "bob-token"


def test_fetch_haoke_todos_returns_cached_items_when_api_fetch_fails(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    monkeypatch.setattr(haoke_client, "user_dir", user_dir)
    monkeypatch.setattr(haoke_client, "has_credentials", lambda username: True)
    monkeypatch.setattr(haoke_client, "_get_token", lambda username: "token")
    monkeypatch.setattr(
        haoke_client,
        "_fetch_all_todos",
        lambda token: (_ for _ in ()).throw(RuntimeError("network down")),
    )
    (user_dir("alice") / "haoke_cache.json").write_text(
        '[{"id": 7, "title": "cached haoke"}]',
        encoding="utf-8",
    )

    result = haoke_client.fetch_haoke_todos("alice")

    assert result == {"ok": True, "data": [{"id": 7, "title": "cached haoke"}], "cached": True}


def test_get_cached_todos_reports_mtime_and_staleness(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    monkeypatch.setattr(haoke_client, "user_dir", user_dir)
    monkeypatch.setattr(haoke_client, "HAOKE_CACHE_TTL_SECONDS", 60)
    cache_file = user_dir("alice") / "haoke_cache.json"
    cache_file.write_text('[{"id": 8, "title": "cached"}]', encoding="utf-8")
    fetched_at = cache_file.stat().st_mtime

    fresh = haoke_client.get_cached_todos("alice", now=fetched_at + 30)
    stale = haoke_client.get_cached_todos("alice", now=fetched_at + 90)

    assert fresh["ok"] is True
    assert fresh["data"] == [{"id": 8, "title": "cached"}]
    assert fresh["cached"] is True
    assert fresh["fetched_at"] == fetched_at
    assert fresh["stale"] is False
    assert stale["stale"] is True


def test_get_cached_todos_returns_none_when_cache_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(haoke_client, "user_dir", _user_dir(tmp_path))

    assert haoke_client.get_cached_todos("alice") is None


def test_start_background_refresh_starts_once_per_user(monkeypatch):
    started = []
    runners = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append((self.args, self.daemon))
            runners.append((self.target, self.args))

    monkeypatch.setattr(haoke_client.threading, "Thread", FakeThread)

    assert haoke_client.start_background_refresh("alice") is True
    assert haoke_client.start_background_refresh("alice") is False
    assert haoke_client.start_background_refresh("bob") is True

    assert started == [(("alice",), True), (("bob",), True)]
    runners[0][0](*runners[0][1])

    assert haoke_client.start_background_refresh("alice") is True
