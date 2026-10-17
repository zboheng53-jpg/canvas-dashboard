import json

import apple_calendar
import pytest
from icalendar import Calendar
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
    assert "DTSTART;TZID=Asia/Shanghai:20260711T195900" in calendar
    assert "DTEND;TZID=Asia/Shanghai:20260711T200000" in calendar
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


def test_calendar_advertises_refresh_interval():
    calendar = Calendar.from_ical(apple_calendar.build_calendar(
        "alice", [], now=datetime(2026, 10, 17, tzinfo=apple_calendar.CST),
    ))

    assert calendar.decoded("REFRESH-INTERVAL") == timedelta(minutes=15)
    assert str(calendar["X-PUBLISHED-TTL"]) == "PT15M"


def test_calendar_folds_utf8_lines_without_changing_event_contents():
    title = "力学原理A：桁架、摩擦与受力分析；" * 8
    description = "课程说明\r\n第二行\r第三行\n" + "详细要求与提交地址" * 15
    body = apple_calendar.build_calendar(
        "alice",
        [{"source": "Ketangpai", "id": "ktp_hw_1", "title": title,
          "description": description, "due_ts": "2026-10-18T23:59:00+08:00"}],
        now=datetime(2026, 10, 17, tzinfo=apple_calendar.CST),
    )

    assert all(len(line.encode("utf-8")) <= 75 for line in body.split("\r\n"))
    assert "\n" not in body.replace("\r\n", "")
    assert "\r" not in body.replace("\r\n", "")
    event, = Calendar.from_ical(body).walk("VEVENT")
    assert str(event["SUMMARY"]) == title
    assert str(event["DESCRIPTION"]).endswith(description.replace("\r\n", "\n").replace("\r", "\n"))
    assert event.decoded("DTSTART") == datetime(2026, 10, 18, 23, 58, tzinfo=apple_calendar.CST)
    assert event.decoded("DTEND") == datetime(2026, 10, 18, 23, 59, tzinfo=apple_calendar.CST)


@pytest.mark.parametrize("due_ts,start,end", [
    ("2026-10-28T23:59:00+08:00", "2026-10-28T23:58:00+08:00", "2026-10-28T23:59:00+08:00"),
    ("2026-10-29T00:00:00+08:00", "2026-10-28T23:59:00+08:00", "2026-10-29T00:00:00+08:00"),
    ("2026-11-01T00:00:00+08:00", "2026-10-31T23:59:00+08:00", "2026-11-01T00:00:00+08:00"),
    ("2027-01-01T00:00:00+08:00", "2026-12-31T23:59:00+08:00", "2027-01-01T00:00:00+08:00"),
    ("2026-10-29T14:00:00+08:00", "2026-10-29T13:59:00+08:00", "2026-10-29T14:00:00+08:00"),
    ("2026-10-28T23:59:59+08:00", "2026-10-28T23:58:00+08:00", "2026-10-28T23:59:00+08:00"),
    ("2026-10-29T00:00:30+08:00", "2026-10-28T23:59:00+08:00", "2026-10-29T00:00:00+08:00"),
    ("2026-10-29T00:01:00+08:00", "2026-10-29T00:00:00+08:00", "2026-10-29T00:01:00+08:00"),
    ("2026-10-28T16:00:00Z", "2026-10-28T23:59:00+08:00", "2026-10-29T00:00:00+08:00"),
    ("2026-10-29T00:00:00", "2026-10-28T23:59:00+08:00", "2026-10-29T00:00:00+08:00"),
])
def test_deadline_marker_and_alert_are_independent(due_ts, start, end):
    original = {"source": "Ketangpai", "id": "hw1", "title": "作业", "due_ts": due_ts}
    body = apple_calendar.build_calendar("alice", [original], now=datetime(2026, 10, 17, tzinfo=apple_calendar.CST))
    event, = Calendar.from_ical(body).walk("VEVENT")

    assert event.decoded("DTSTART").isoformat() == start
    assert event.decoded("DTEND").isoformat() == end
    assert event.decoded("DTEND") - event.decoded("DTSTART") == timedelta(minutes=1)
    assert str(event["UID"]) == "ketangpai-hw1@canvas-dashboard"
    assert str(event["SUMMARY"]) == "作业"
    assert str(event["TRANSP"]) == "TRANSPARENT"
    actual_due = datetime.fromisoformat(due_ts.replace("Z", "+00:00"))
    actual_due = actual_due.replace(tzinfo=apple_calendar.CST) if actual_due.tzinfo is None else actual_due.astimezone(apple_calendar.CST)
    assert actual_due.strftime("%Y-%m-%d %H:%M:%S") in str(event["DESCRIPTION"])
    alarm, = event.walk("VALARM")
    assert str(alarm["ACTION"]) == "DISPLAY"
    assert alarm.decoded("TRIGGER") == actual_due - timedelta(hours=1)
    assert str(alarm["TRIGGER"].params["VALUE"]) == "DATE-TIME"
    assert "作业" in str(alarm["DESCRIPTION"])
    assert original["due_ts"] == due_ts


@pytest.mark.parametrize("field", ["due_ts", "due_date"])
def test_date_only_deadline_stays_on_its_day_without_invented_alert_time(field):
    body = apple_calendar.build_calendar(
        "alice", [{"source": "Custom", "id": 1, "title": "日期待办", field: "2026-10-28"}],
        now=datetime(2026, 10, 17, tzinfo=apple_calendar.CST),
    )
    event, = Calendar.from_ical(body).walk("VEVENT")
    assert event.decoded("DTSTART").isoformat() == "2026-10-28"
    assert event.decoded("DTEND").isoformat() == "2026-10-29"
    assert not event.walk("VALARM")


def test_real_schedule_keeps_its_span_across_midnight():
    body = apple_calendar.build_calendar(
        "alice", [{"source": "Schedule", "id": 1, "title": "夜间安排",
                   "start_dt": "2026-10-28T23:00:00+08:00", "end_dt": "2026-10-29T01:00:00+08:00"}],
        now=datetime(2026, 10, 17, tzinfo=apple_calendar.CST),
    )
    event, = Calendar.from_ical(body).walk("VEVENT")
    assert event.decoded("DTSTART").isoformat() == "2026-10-28T23:00:00+08:00"
    assert event.decoded("DTEND").isoformat() == "2026-10-29T01:00:00+08:00"
    assert "截止时间" not in str(event["DESCRIPTION"])
    assert not event.walk("VALARM")

