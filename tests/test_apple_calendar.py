import json

import apple_calendar
from datetime import datetime, timezone, timedelta


def test_calendar_token_is_hashed_at_rest_and_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(apple_calendar, "DATA_DIR", tmp_path)
    monkeypatch.setattr(apple_calendar, "user_dir", lambda username: tmp_path / "users" / username)

    alice_token = apple_calendar.create_token("alice")
    bob_token = apple_calendar.create_token("bob")
    stored = json.loads((tmp_path / "users" / "alice" / "apple_calendar.json").read_text(encoding="utf-8"))

    assert alice_token != bob_token
    assert len(alice_token) >= 40
    assert alice_token not in stored.values()
    assert set(stored) == {"token_hash"}
    assert apple_calendar.username_for_token(alice_token) == "alice"
    assert apple_calendar.username_for_token(bob_token) == "bob"


def test_calendar_token_revocation_only_invalidates_its_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(apple_calendar, "DATA_DIR", tmp_path)
    monkeypatch.setattr(apple_calendar, "user_dir", lambda username: tmp_path / "users" / username)

    alice_token = apple_calendar.create_token("alice")
    bob_token = apple_calendar.create_token("bob")

    assert apple_calendar.revoke_token("alice") is True
    assert apple_calendar.username_for_token(alice_token) is None
    assert apple_calendar.username_for_token(bob_token) == "bob"
    assert apple_calendar.revoke_token("alice") is False


def test_calendar_ics_includes_only_active_dated_items():
    cst = timezone(timedelta(hours=8))
    calendar = apple_calendar.build_calendar(
        "alice",
        [
            {"source": "Canvas", "id": 7, "title": "Quiz, Week 1", "due_ts": "2026-07-11T20:00:00+08:00"},
            {"source": "Custom", "id": 8, "title": "Done", "due_ts": "2026-07-12T20:00:00+08:00", "done": True},
            {"source": "Custom", "id": 9, "title": "No date"},
        ],
        now=datetime(2026, 7, 10, 8, 0, tzinfo=cst),
    )

    assert "BEGIN:VCALENDAR" in calendar
    assert "UID:canvas-7@canvas-dashboard" in calendar
    assert "SUMMARY:Quiz\\, Week 1" in calendar
    assert "DTSTART;TZID=Asia/Shanghai:20260711T200000" in calendar
    assert "Done" not in calendar
    assert "No date" not in calendar
