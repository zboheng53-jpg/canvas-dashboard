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


def test_calendar_uses_explicit_stable_uid_and_skips_one_invalid_item():
    cst = timezone(timedelta(hours=8))
    calendar = apple_calendar.build_calendar(
        "alice",
        [
            {
                "source": "Project",
                "id": "renamed",
                "uid": "project-task-7-9@canvas-dashboard",
                "title": "新任务名 · 新项目名",
                "due_date": "2026-08-02",
            },
            {
                "source": "Project",
                "id": "invalid",
                "uid": "project-task-7-10@canvas-dashboard",
                "title": "非法日期",
                "due_date": "not-a-date",
            },
            {
                "source": "Project",
                "id": "due-7",
                "uid": "project-due-7@canvas-dashboard",
                "title": "项目截止 · 新项目名",
                "due_date": "2026-09-01",
            },
        ],
        now=datetime(2026, 7, 10, 8, 0, tzinfo=cst),
    )

    assert "UID:project-task-7-9@canvas-dashboard" in calendar
    assert "UID:project-due-7@canvas-dashboard" in calendar
    assert "SUMMARY:新任务名 · 新项目名" in calendar
    assert "非法日期" not in calendar


def test_calendar_metadata_and_categories_in_ics():
    cst = timezone(timedelta(hours=8))
    calendar = apple_calendar.build_calendar(
        "alice",
        [
            {"source": "Course", "id": 1, "title": "概率论", "start_dt": "2026-09-14T08:00:00+08:00", "end_dt": "2026-09-14T09:35:00+08:00"},
            {"source": "Canvas", "id": 2, "title": "作业1", "due_ts": "2026-09-15T23:59:00+08:00"},
            {"source": "Project", "id": 3, "title": "论文推进", "due_date": "2026-09-16"},
            {"source": "Schedule", "id": 4, "title": "晚自习", "start_dt": "2026-09-14T19:00:00+08:00", "end_dt": "2026-09-14T21:00:00+08:00"},
        ],
        now=datetime(2026, 9, 14, 8, 0, tzinfo=cst),
        cal_name="Canvas Dashboard · 课表",
        cal_color="#2563EB",
    )

    assert "X-WR-CALNAME:Canvas Dashboard · 课表" in calendar
    assert "NAME:Canvas Dashboard · 课表" in calendar
    assert "X-APPLE-CALENDAR-COLOR:#2563EB" in calendar
    assert "CATEGORIES:Course" in calendar
    assert "COLOR:#2563EB" in calendar
    assert "CATEGORIES:Assignment" in calendar
    assert "COLOR:#DC2626" in calendar
    assert "CATEGORIES:Project" in calendar
    assert "COLOR:#EA580C" in calendar
    assert "CATEGORIES:Schedule" in calendar
    assert "COLOR:#059669" in calendar

