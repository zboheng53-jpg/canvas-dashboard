import json
from datetime import date, timedelta

import app as dashboard_app
import schedule_store
import tongji_timetable
import user_paths


def _client(tmp_path, monkeypatch, username="alice"):
    def resolve_user_dir(name):
        path = tmp_path / "users" / name
        path.mkdir(parents=True, exist_ok=True)
        return path
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", resolve_user_dir)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session:
        session["username"] = username
        session["_csrf_token"] = f"csrf-{username}"
    client.csrf_headers = {"X-CSRF-Token": f"csrf-{username}"}
    return client, resolve_user_dir


def test_parse_selected_courses_uses_headers_and_handles_week_patterns():
    markup = """
    <table><tr><th>教师</th><th>上课地点</th><th>课程名称</th><th>上课时间</th><th>课程代码</th></tr>
    <tr><td>张老师</td><td>北229</td><td>高等数学</td><td>周一第1-2节[1-16周]；周三第3-4节单周</td><td>MATH1</td></tr>
    <tr><td>李老师</td><td>南329</td><td>实践课</td><td>2026-04-01至2026-04-03 第5-6节</td><td>LAB1</td></tr></table>
    """
    courses = tongji_timetable.parse_selected_courses_html(markup)
    assert [course["code"] for course in courses] == ["MATH1", "LAB1"]
    assert courses[0]["sessions"][0]["weeks"] == list(range(1, 17))
    assert courses[0]["sessions"][0]["start_time"] == "08:00"
    assert courses[0]["sessions"][0]["end_time"] == "09:35"
    assert courses[0]["sessions"][1]["parity"] == "odd"
    assert tongji_timetable.parse_time_segments("周四第1-2节[1-16]")[0]["weeks"] == list(range(1, 17))
    assert tongji_timetable.parse_time_segments("周四第1-2节双周")[0]["parity"] == "even"
    assert courses[1]["sessions"][0]["date_start"] == "2026-04-01"
    assert courses[1]["sessions"][0]["date_end"] == "2026-04-03"


def test_parse_time_segments_supports_specified_weeks_multiple_locations_and_periods():
    sessions = tongji_timetable.parse_time_segments("周二第7-8节第1、3、5周 南329；周五第9-10节 东校区实验楼")
    assert len(sessions) == 2
    assert sessions[0]["weeks"] == [1, 3, 5]
    assert (sessions[0]["start_time"], sessions[0]["end_time"]) == ("15:30", "17:05")
    assert sessions[1]["location"] == "东校区实验楼"


def test_refresh_failure_keeps_previous_course_cache(tmp_path, monkeypatch):
    client, resolve_user_dir = _client(tmp_path, monkeypatch)
    schedule_store.save_courses("alice", "测试学期", "2026-03-02", [{"name": "旧课程", "sessions": []}], "2026-03-01T00:00:00+08:00")
    monkeypatch.setattr(dashboard_app.tongji_timetable, "fetch_selected_courses", lambda: None)
    response = client.post("/api/schedule/refresh", headers=client.csrf_headers)
    assert response.status_code == 502
    assert json.loads((resolve_user_dir("alice") / "course_schedule.json").read_text(encoding="utf-8"))["courses"][0]["name"] == "旧课程"


def test_schedule_items_are_isolated_and_overlap_is_reported(tmp_path, monkeypatch):
    alice, _ = _client(tmp_path, monkeypatch, "alice")
    schedule_store.save_courses("alice", "测试学期", "2026-03-02", [{"name": "课程", "sessions": [{"weekday": 0, "start_time": "08:00", "end_time": "09:30"}]}], "2026-03-01T00:00:00+08:00")
    recurring = alice.post("/api/schedule/recurring", json={"title": "阅读", "weekday": 0, "start_time": "09:00", "end_time": "10:30"}, headers=alice.csrf_headers)
    assert recurring.get_json()["overlap"] is True
    response = alice.post("/api/schedule/one-off", json={"title": "答辩", "date": "2026-07-20", "start_time": "10:00", "end_time": "11:00"}, headers=alice.csrf_headers)
    assert response.get_json()["overlap"] is True
    overlap = alice.post("/api/schedule/one-off", json={"title": "讨论", "date": "2026-07-20", "start_time": "10:30", "end_time": "11:30"}, headers=alice.csrf_headers)
    assert overlap.get_json()["overlap"] is True
    bob, _ = _client(tmp_path, monkeypatch, "bob")
    assert bob.get("/api/schedule").get_json()["items"]["one_off"] == []


def test_one_off_items_on_different_dates_do_not_overlap(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    first = client.post(
        "/api/schedule/one-off",
        json={"title": "第一次讨论", "date": "2026-07-20", "start_time": "10:00", "end_time": "11:00"},
        headers=client.csrf_headers,
    )
    second = client.post(
        "/api/schedule/one-off",
        json={"title": "第二次讨论", "date": "2026-07-27", "start_time": "10:30", "end_time": "11:30"},
        headers=client.csrf_headers,
    )

    assert first.get_json()["overlap"] is False
    assert second.get_json()["overlap"] is False


def test_recurring_item_can_pause_skip_edit_and_delete(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    created = client.post("/api/schedule/recurring", json={"title": "阅读", "weekday": 0, "start_time": "08:00", "end_time": "09:00"}, headers=client.csrf_headers).get_json()["item"]
    updated = client.put(f"/api/schedule/recurring/{created['id']}", json={"title": "阅读", "weekday": 0, "start_time": "08:30", "end_time": "09:30", "enabled": False, "skipped_dates": ["2026-07-20"]}, headers=client.csrf_headers)
    assert updated.get_json()["item"]["skipped_dates"] == ["2026-07-20"]
    assert updated.get_json()["item"]["enabled"] is False
    assert client.delete(f"/api/schedule/recurring/{created['id']}", headers=client.csrf_headers).get_json()["ok"] is True


def test_schedule_mutations_require_authentication_and_csrf(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    with dashboard_app.app.test_client() as anonymous:
        assert anonymous.get("/api/schedule/today").status_code == 401
    blocked = client.post("/api/schedule/recurring", json={"title": "阅读", "weekday": 0, "start_time": "08:00", "end_time": "09:00"})
    assert blocked.status_code == 403


def test_today_schedule_only_returns_busy_items_and_date_only_deadlines(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    today = date.today()
    semester_start = today - timedelta(days=today.weekday())
    schedule_store.save_courses("alice", "测试学期", semester_start.isoformat(), [{"name": "自动控制", "location": "北229", "sessions": [{"weekday": today.weekday(), "weeks": [1], "parity": None, "start_time": "08:00", "end_time": "09:35", "date_start": None, "date_end": None, "location": "北229"}]}], "2026-07-01T00:00:00+08:00")
    schedule_store.create_item("alice", "recurring", {"title": "实验", "weekday": today.weekday(), "start_time": "10:00", "end_time": "11:00", "enabled": True})
    schedule_store.create_item("alice", "one_off", {"title": "组会", "date": today.isoformat(), "start_time": "14:00", "end_time": "15:00"})
    dashboard_app._save_todos("alice", [{"id": 1, "text": "实验报告", "done": False, "due_date": today.isoformat(), "subtasks": []}])
    monkeypatch.setattr(dashboard_app, "get_term_info", lambda: ("测试学期", 1, semester_start.isoformat()))
    data = client.get("/api/schedule/today").get_json()
    assert [item["title"] for item in data["timed"]] == ["自动控制", "实验", "组会"]
    assert data["deadlines"] == [{"title": "实验报告"}]
