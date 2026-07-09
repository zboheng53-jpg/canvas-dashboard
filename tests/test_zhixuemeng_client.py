import base64
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import zhixuemeng_client


def _user_dir(root: Path):
    def resolve(username):
        path = root / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    return resolve


def fake_jwt(username: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"username": username}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.fixture(autouse=True)
def clear_token_cache():
    zhixuemeng_client._token_cache.clear()
    yield
    zhixuemeng_client._token_cache.clear()


def test_fetch_courses_filters_by_jwt_username_dedupes_and_sorts(monkeypatch):
    token = fake_jwt("zxm_alice")
    seen_params = []
    monkeypatch.setattr(zhixuemeng_client, "_get_token", lambda username: token)

    class Response:
        def json(self):
            return {
                "success": True,
                "result": {
                    "records": [
                        {"courseCode": "B02", "courseName": "B", "className": "2", "semester_dictText": "S"},
                        {"courseCode": "A01", "courseName": "A", "className": "1", "semester_dictText": "S"},
                        {"courseCode": "A01", "courseName": "A duplicate", "className": "1", "semester_dictText": "S"},
                    ]
                },
            }

    def fake_get(url, params, headers, timeout):
        seen_params.append(params)
        assert headers["X-Access-Token"] == token
        return Response()

    monkeypatch.setattr(zhixuemeng_client.requests, "get", fake_get)

    result = zhixuemeng_client.fetch_courses("alice")

    assert seen_params == [{"pageSize": "10000", "username": "zxm_alice"}]
    assert result == {
        "ok": True,
        "courses": [
            {"courseCode": "A01", "courseName": "A", "className": "1", "semester": "S"},
            {"courseCode": "B02", "courseName": "B", "className": "2", "semester": "S"},
        ],
    }


def test_fetch_assignments_scans_all_courses_writes_cache_and_filters_course(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    token = fake_jwt("zxm_alice")
    monkeypatch.setattr(zhixuemeng_client, "user_dir", user_dir)
    monkeypatch.setattr(zhixuemeng_client, "_get_token", lambda username: token)
    monkeypatch.setattr(zhixuemeng_client.time_module, "time", lambda: 1000)

    class Response:
        def json(self):
            return {
                "success": True,
                "result": {
                    "records": [
                        {"courseCode": "B02"},
                        {"courseCode": "A01"},
                        {"courseCode": "A01"},
                    ]
                },
            }

    monkeypatch.setattr(zhixuemeng_client.requests, "get", lambda url, params, headers, timeout: Response())

    def fake_scan(token_arg, course_code):
        assert token_arg == token
        return [
            {
                "id": f"zxm_{course_code}",
                "title": f"Task {course_code}",
                "course": course_code,
                "due_str": "07-10 08:00",
                "due_ts": f"2099-07-10T0{1 if course_code == 'A01' else 2}:00:00+08:00",
                "type": "assignment",
                "type_raw": "assignment",
                "url": f"https://h5.zhixuemeng.com/#/pages/class/banji_bjzy?courseCode={course_code}",
            }
        ]

    monkeypatch.setattr(zhixuemeng_client, "_scan_course", fake_scan)

    result = zhixuemeng_client.fetch_assignments("alice", "A01")

    assert result["ok"] is True
    assert result["cached"] is False
    assert [item["id"] for item in result["items"]] == ["zxm_A01"]
    cache = json.loads((user_dir("alice") / "zhixuemeng_cache.json").read_text(encoding="utf-8"))
    assert cache["_user"] == "zxm_alice"
    assert [item["id"] for item in cache["items"]] == ["zxm_A01", "zxm_B02"]


def test_fetch_assignments_uses_cache_for_same_jwt_user(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    token = fake_jwt("zxm_alice")
    monkeypatch.setattr(zhixuemeng_client, "user_dir", user_dir)
    monkeypatch.setattr(zhixuemeng_client, "_get_token", lambda username: token)
    monkeypatch.setattr(zhixuemeng_client.time_module, "time", lambda: 1000)
    (user_dir("alice") / "zhixuemeng_cache.json").write_text(
        json.dumps(
            {
                "_ts": 900,
                "_user": "zxm_alice",
                "items": [
                    {
                        "id": "zxm_A01",
                        "url": "https://h5.zhixuemeng.com/#/pages/class/banji_bjzy?courseCode=A01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_if_network(*args, **kwargs):
        raise AssertionError("fresh course scan should not run when cache is valid")

    monkeypatch.setattr(zhixuemeng_client.requests, "get", fail_if_network)

    result = zhixuemeng_client.fetch_assignments("alice")

    assert result == {
        "ok": True,
        "items": [
            {
                "id": "zxm_A01",
                "url": "https://h5.zhixuemeng.com/#/pages/class/banji_bjzy?courseCode=A01",
            }
        ],
        "cached": True,
    }


def test_logout_removes_token_selected_course_and_assignment_cache(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    monkeypatch.setattr(zhixuemeng_client, "user_dir", user_dir)
    zhixuemeng_client._token_cache["alice"] = {
        "token": "token",
        "expires_at": datetime.now(zhixuemeng_client.CST) + timedelta(hours=1),
    }
    config_file = user_dir("alice") / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "zhixuemeng_token_encrypted": "encrypted",
                "zhixuemeng_selected_course": "A01",
                "calendar_feed_url": "keep-me",
            }
        ),
        encoding="utf-8",
    )
    cache_file = user_dir("alice") / "zhixuemeng_cache.json"
    cache_file.write_text('{"items": [{"id": "old"}]}', encoding="utf-8")

    zhixuemeng_client.logout("alice")

    config = json.loads(config_file.read_text(encoding="utf-8"))
    assert "alice" not in zhixuemeng_client._token_cache
    assert "zhixuemeng_token_encrypted" not in config
    assert "zhixuemeng_selected_course" not in config
    assert config["calendar_feed_url"] == "keep-me"
    assert not cache_file.exists()
