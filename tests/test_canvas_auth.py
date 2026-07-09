from pathlib import Path

import pytest
import requests

import canvas_auth


def _user_dir(root: Path):
    def resolve(username):
        path = root / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    return resolve


def test_parse_ical_extracts_canvas_id_course_and_cst_due_time():
    raw = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:assignment-uid
SUMMARY:Lab report
DESCRIPTION:Course: Control Systems
URL:https://canvas.example/courses/1/assignments/123#assignment_123
DTSTART:20990710T010000Z
END:VEVENT
END:VCALENDAR
"""

    items = canvas_auth._parse_ical(raw)

    assert len(items) == 1
    assert items[0]["id"] == 123
    assert items[0]["title"] == "Lab report"
    assert items[0]["course"] == "Control Systems"
    assert items[0]["due_str"] == "07-10 09:00"
    assert items[0]["due_ts"] == "2099-07-10T09:00:00+08:00"
    assert items[0]["type_raw"] == "assignment"
    assert items[0]["url"] == "https://canvas.example/courses/1/assignments/123#assignment_123"


def test_parse_ical_skips_past_and_missing_due_events():
    raw = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:past
SUMMARY:Past
DTSTART:20000101T000000Z
END:VEVENT
BEGIN:VEVENT
UID:no-due
SUMMARY:No due
END:VEVENT
END:VCALENDAR
"""

    assert canvas_auth._parse_ical(raw) == []


def test_extract_stable_id_hashes_uid_when_url_has_no_canvas_fragment():
    first = canvas_auth._extract_stable_id("https://canvas.example/events/abc", "uid-1")
    second = canvas_auth._extract_stable_id("https://canvas.example/events/abc", "uid-1")
    other = canvas_auth._extract_stable_id("https://canvas.example/events/abc", "uid-2")

    assert first == second
    assert first != other
    assert 0 <= first < 1000000


def test_fetch_canvas_planner_writes_cache_on_success(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    monkeypatch.setattr(canvas_auth, "user_dir", user_dir)
    (user_dir("alice") / "config.json").write_text(
        '{"calendar_feed_url": "https://canvas.example/feed.ics"}',
        encoding="utf-8",
    )

    class Response:
        status_code = 200
        text = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:assignment-uid
SUMMARY:Cached item
URL:https://canvas.example/#assignment_456
DTSTART:20990710T010000Z
END:VEVENT
END:VCALENDAR
"""

    monkeypatch.setattr(canvas_auth.requests, "get", lambda url, timeout: Response())

    result = canvas_auth.fetch_canvas_planner("alice")

    assert result["ok"] is True
    assert result["cached"] is False
    assert result["data"][0]["id"] == 456
    assert "Cached item" in (user_dir("alice") / "canvas_cache.json").read_text(encoding="utf-8")


def test_fetch_canvas_planner_falls_back_to_cache_on_request_failure(tmp_path, monkeypatch):
    user_dir = _user_dir(tmp_path)
    monkeypatch.setattr(canvas_auth, "user_dir", user_dir)
    (user_dir("alice") / "config.json").write_text(
        '{"calendar_feed_url": "https://canvas.example/feed.ics"}',
        encoding="utf-8",
    )
    (user_dir("alice") / "canvas_cache.json").write_text(
        '[{"id": 1, "title": "cached"}]',
        encoding="utf-8",
    )

    def raise_timeout(url, timeout):
        raise requests.Timeout("boom")

    monkeypatch.setattr(canvas_auth.requests, "get", raise_timeout)

    result = canvas_auth.fetch_canvas_planner("alice")

    assert result == {"ok": True, "data": [{"id": 1, "title": "cached"}], "cached": True}
