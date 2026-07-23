import json
from io import BytesIO
from datetime import date, timedelta
from zipfile import ZipFile
from xml.sax.saxutils import escape

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


def _exported_timetable_xlsx(rows):
    def cell(column, row_number, value):
        return f'<c r="{column}{row_number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    sheet_rows = "".join(
        f'<row r="{row_number}">{"".join(cell(chr(65 + index), row_number, value) for index, value in enumerate(row))}</row>'
        for row_number, row in enumerate(rows, start=1)
    )
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{sheet_rows}</sheetData></worksheet>')
    return output.getvalue()


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


def test_visual_grid_filters_courses_without_overwriting_list_meeting_times():
    tables = [
        [["新课程序号", "课程名称", "教师", "上课时间", "上课地点"]],
        [["AUTO1001", "匿名课程", "匿名教师", "星期二 7-8节 [11-14]", "北229"]],
        [
            ["节次/周次", "周一", "周二", "周三", "周四", "周五", "周六", "周日"],
            ["第7节课", "匿名教师 匿名课程(AUTO1001) [11-14] 北229", "", "", "", "", "", ""],
        ],
    ]

    courses = tongji_timetable._parse_selected_courses_tables(tables)

    assert len(courses) == 1
    assert courses[0]["sessions"] == tongji_timetable.parse_time_segments(
        "星期二 7-8节 [11-14]", "北229"
    )
    assert courses[0]["sessions"][0]["weekday"] == 1


def test_reference_timetable_maps_every_course_for_weeks_1_to_16():
    raw_times = {
        "CST160202": "星期三 5-6节 [7-16],星期三 5-6节 [1-6]",
        "CMS120407": "星期三 3-4节 [1, 3, 5, 7, 9, 11, 13, 15],星期一 1-2节 [1-16],星期五 5-6节 [1-16]",
        "DPE1102A4": "星期四 3-4节 [1-16]",
        "CST120102": "星期一 3-4节 [1-16]",
        "PSE121601": "星期四 1-2节 [1-16],星期三 7-8节 [2-16双]",
        "PSE161001": "星期五 1-2节 [1-16]",
        "CSE121003": "星期二 1-2节 [1-16],星期三 7-8节 [1, 3, 5, 7, 9, 11, 13, 15]",
        "CMS121702": "星期一 9-11节 [1-16],星期五 3-4节 [1-16]",
        "QDC190111": "星期一 5-8节 [4],星期四 5-8节 [7-8],星期一 5-8节 [7-8],星期一 5-8节 [5-6],星期一 5-8节 [11-16],星期四 5-8节 [9-10],星期一 5-8节 [9-10],星期一 5-8节 [1-3],星期四 5-8节 [1-4],星期四 5-8节 [11-16],星期四 5-8节 [5-6]",
        "CMA110111": "星期三 9-11节 [1-16]",
        "CMA110421": "星期二 7-8节 [11-14]",
    }
    tables = [
        [["新课程序号", "课程名称", "上课时间"]],
        [[code, code, raw_time] for code, raw_time in raw_times.items()],
    ]

    courses = tongji_timetable._parse_selected_courses_tables(tables)

    always = {
        (0, 1, 2, "CMS120407"), (0, 3, 4, "CST120102"),
        (0, 5, 8, "QDC190111"), (0, 9, 11, "CMS121702"),
        (1, 1, 2, "CSE121003"),
        (2, 5, 6, "CST160202"), (2, 9, 11, "CMA110111"),
        (3, 1, 2, "PSE121601"), (3, 3, 4, "DPE1102A4"),
        (3, 5, 8, "QDC190111"),
        (4, 1, 2, "PSE161001"), (4, 3, 4, "CMS121702"),
        (4, 5, 6, "CMS120407"),
    }
    for week in range(1, 17):
        actual = {
            (session["weekday"], session["start_period"], session["end_period"], course["code"])
            for course in courses
            for session in course["sessions"]
            if (not session["weeks"] or week in session["weeks"])
            and (session["parity"] != "odd" or week % 2 == 1)
            and (session["parity"] != "even" or week % 2 == 0)
        }
        expected = set(always)
        if week % 2:
            expected.add((2, 3, 4, "CMS120407"))
        expected.add((2, 7, 8, "CSE121003" if week % 2 else "PSE121601"))
        if 11 <= week <= 14:
            expected.add((1, 7, 8, "CMA110421"))
        assert actual == expected, f"第{week}周映射不一致"


def test_authenticated_cdp_reader_opens_timetable_from_workbench(monkeypatch):
    class Link:
        def __init__(self):
            self.clicked = False

        def is_visible(self):
            return True

        def click(self):
            self.clicked = True

    class Locator:
        def __init__(self, link):
            self.link = link

        def count(self):
            return 1

        def nth(self, index):
            assert index == 0
            return self.link

    class Page:
        url = "https://1.tongji.edu.cn/workbench"

        def __init__(self):
            self.link = Link()
            self.waited = None
            self.goto_called = False

        def get_by_text(self, text, exact):
            assert (text, exact) == ("查看课表", True)
            return Locator(self.link)

        def wait_for_timeout(self, timeout):
            self.waited = timeout

        def goto(self, *args, **kwargs):
            self.goto_called = True

        def wait_for_selector(self, selector, timeout):
            assert selector == "table"
            assert timeout == 20_000

        def content(self):
            return "<table></table>"

    class Context:
        def __init__(self, page):
            self.pages = [page]

    class Browser:
        def __init__(self, page):
            self.contexts = [Context(page)]

    class Playwright:
        def __init__(self, page):
            self.chromium = type("Chromium", (), {"connect_over_cdp": lambda _, endpoint: Browser(page)})()

    class PlaywrightContext:
        def __init__(self, page):
            self.page = page

        def __enter__(self):
            return Playwright(self.page)

        def __exit__(self, *args):
            return False

    page = Page()
    monkeypatch.setattr(tongji_timetable, "_playwright", lambda: PlaywrightContext(page))
    monkeypatch.setattr(tongji_timetable, "_wait_for_selected_courses", lambda current_page: [{"name": "测试课程"}])

    assert tongji_timetable.fetch_selected_courses_from_cdp("http://127.0.0.1:6300") == [{"name": "测试课程"}]
    assert page.link.clicked is True
    assert page.waited == 1_000
    assert page.goto_called is False


def test_authenticated_cdp_reader_waits_until_courses_are_rendered(monkeypatch):
    class Page:
        def __init__(self):
            self.waits = []

        def wait_for_timeout(self, timeout):
            self.waits.append(timeout)

    page = Page()
    visible_tables = iter([[], [[["课程名称", "上课时间"], ["测试课程", "周一 1-2节 [1-16]"]]]])
    monkeypatch.setattr(tongji_timetable, "_visible_timetable_tables", lambda _: next(visible_tables))

    courses = tongji_timetable._wait_for_selected_courses(page, timeout_ms=60_000)

    assert [course["name"] for course in courses] == ["测试课程"]
    assert page.waits == [1_000]


def test_parse_live_timetable_split_tables_and_xingqi_time_format():
    markup = """
    <table><tr><th></th><th>新课程序号</th><th>课程名称</th><th>教师</th><th>上课时间</th><th>上课地点</th><th>校区</th></tr></table>
    <table><tr><td></td><td>AUTO1001</td><td>匿名课程</td><td>匿名教师</td>
    <td>星期一 1-2节 [1-16],星期三 7-8节 [2-16双]</td><td>匿名教室</td><td>四平路校区</td></tr></table>
    """

    courses = tongji_timetable.parse_selected_courses_html(markup)

    assert len(courses) == 1
    assert courses[0]["code"] == "AUTO1001"
    assert len(courses[0]["sessions"]) == 2
    assert courses[0]["sessions"][0]["weekday"] == 0
    assert courses[0]["sessions"][0]["weeks"] == list(range(1, 17))
    assert courses[0]["sessions"][0]["location"] == "四平路校区 · 匿名教室"
    assert courses[0]["sessions"][1]["parity"] == "even"


def test_import_exported_timetable_xlsx_replaces_only_current_users_courses(tmp_path, monkeypatch):
    client, resolve_user_dir = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(dashboard_app, "get_term_info", lambda: ("2025-2026学年第2学期", 1, "2026-03-02"))
    content = _exported_timetable_xlsx([
        ["新课程序号", "课程名称", "教师", "上课时间", "上课地点", "校区"],
        ["AUTO1001", "自动控制原理", "匿名教师", "星期一 1-2节 [1-16]，星期三 7-8节 [2-16双]", "匿名教室", "四平路校区"],
    ])

    response = client.post(
        "/api/schedule/import",
        data={"course_file": (BytesIO(content), "同济大学课程表.xlsx")},
        content_type="multipart/form-data",
        headers=client.csrf_headers,
    )

    assert response.status_code == 200
    stored = json.loads((resolve_user_dir("alice") / "course_schedule.json").read_text(encoding="utf-8"))
    assert stored["term"] == "2025-2026学年第2学期"
    assert stored["courses"][0]["name"] == "自动控制原理"
    assert len(stored["courses"][0]["sessions"]) == 2
    assert stored["courses"][0]["sessions"][1]["parity"] == "even"


def test_import_invalid_timetable_file_keeps_previous_course_cache(tmp_path, monkeypatch):
    client, resolve_user_dir = _client(tmp_path, monkeypatch)
    schedule_store.save_courses("alice", "测试学期", "2026-03-02", [{"name": "旧课程", "sessions": []}], "2026-03-01T00:00:00+08:00")

    response = client.post(
        "/api/schedule/import",
        data={"course_file": (BytesIO(b"not an xlsx"), "课程表.xlsx")},
        content_type="multipart/form-data",
        headers=client.csrf_headers,
    )

    assert response.status_code == 400
    assert json.loads((resolve_user_dir("alice") / "course_schedule.json").read_text(encoding="utf-8"))["courses"][0]["name"] == "旧课程"


def test_refresh_failure_keeps_previous_course_cache(tmp_path, monkeypatch):
    client, resolve_user_dir = _client(tmp_path, monkeypatch)
    schedule_store.save_courses("alice", "测试学期", "2026-03-02", [{"name": "旧课程", "sessions": []}], "2026-03-01T00:00:00+08:00")
    def fail_login(username, password):
        assert (username, password) == ("alice_no", "wrong")
        raise tongji_timetable.TimetableLoginError("登录未完成")
    monkeypatch.setattr(dashboard_app.tongji_timetable, "fetch_selected_courses_with_credentials", fail_login)
    response = client.post("/api/schedule/refresh", json={"username": "alice_no", "password": "wrong"}, headers=client.csrf_headers)
    assert response.status_code == 401
    assert json.loads((resolve_user_dir("alice") / "course_schedule.json").read_text(encoding="utf-8"))["courses"][0]["name"] == "旧课程"


def test_refresh_uses_entered_credentials_and_keeps_them_out_of_storage(tmp_path, monkeypatch):
    client, resolve_user_dir = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dashboard_app.tongji_timetable,
        "fetch_selected_courses_with_credentials",
        lambda username, password: [{"name": f"{username}:{password}", "sessions": []}],
    )
    response = client.post("/api/schedule/refresh", json={"username": "alice_no", "password": "secret"}, headers=client.csrf_headers)
    assert response.status_code == 200
    saved = json.loads((resolve_user_dir("alice") / "course_schedule.json").read_text(encoding="utf-8"))
    assert saved["courses"][0]["name"] == "alice_no:secret"
    assert not (resolve_user_dir("alice") / "config.json").exists()


def test_refresh_requires_tongji_credentials(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/api/schedule/refresh", json={"username": "", "password": ""}, headers=client.csrf_headers)
    assert response.status_code == 400
    assert response.get_json()["code"] == "timetable_credentials_required"


def test_tongji_login_session_creates_an_isolated_vnc_window(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dashboard_app.tongji_login_sessions,
        "create_session",
        lambda username: {
            "username": username,
            "token": "tok_123456789012",
            "port": 6207,
            "url": "/schedule/session/tok_123456789012/",
            "expires_at": 2000,
        },
    )

    response = client.post("/api/schedule/login-session", headers=client.csrf_headers)

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "token": "tok_123456789012",
        "url": "/schedule/session/tok_123456789012/",
        "expires_at": 2000,
    }


def test_tongji_login_session_completion_imports_courses_then_stops_session(tmp_path, monkeypatch):
    client, resolve_user_dir = _client(tmp_path, monkeypatch)
    stopped = []
    monkeypatch.setattr(
        dashboard_app.tongji_login_sessions,
        "session_for_token",
        lambda token: {"username": "alice", "token": token, "debug_port": 6307},
    )
    monkeypatch.setattr(
        dashboard_app.tongji_timetable,
        "fetch_selected_courses_from_cdp",
        lambda endpoint: [{"name": "自动控制原理", "sessions": []}],
    )
    monkeypatch.setattr(
        dashboard_app.tongji_login_sessions,
        "stop_session",
        lambda username, token: stopped.append((username, token)) or True,
    )
    monkeypatch.setattr(dashboard_app, "get_term_info", lambda: ("测试学期", 1, "2026-03-02"))

    response = client.post(
        "/api/schedule/login-session/tok_123456789012/complete",
        headers=client.csrf_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert stopped == [("alice", "tok_123456789012")]
    saved = json.loads((resolve_user_dir("alice") / "course_schedule.json").read_text(encoding="utf-8"))
    assert saved["courses"] == [{"name": "自动控制原理", "sessions": []}]


def test_timetable_extension_is_linked_and_downloadable(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    package_url = "/static/downloads/tongji-timetable-exporter-v1.2.zip"
    page = client.get("/").get_data(as_text=True)

    assert package_url in page
    assert 'id="schedule-import-button"' in page
    assert 'id="schedule-file-input"' in page
    assert "/api/schedule/import" in page
    response = client.get(package_url)
    assert response.status_code == 200
    with ZipFile(BytesIO(response.data)) as archive:
        names = set(archive.namelist())
    expected = {
        "tongji-timetable-exporter-v1.2/README.md",
        "tongji-timetable-exporter-v1.2/manifest.json",
        "tongji-timetable-exporter-v1.2/popup.css",
        "tongji-timetable-exporter-v1.2/popup.html",
        "tongji-timetable-exporter-v1.2/popup.js",
        "tongji-timetable-exporter-v1.2/table-exporter.mjs",
    }
    assert expected <= names


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
    dashboard_app._save_todos("alice", [{"id": 1, "text": "Python学习", "done": False, "due_date": None, "subtasks": [{"id": 1, "text": "周度复盘", "done": False, "due_date": today.isoformat()}]}, {"id": 2, "text": "实验报告", "done": False, "due_date": today.isoformat(), "subtasks": []}])
    monkeypatch.setattr(dashboard_app, "get_term_info", lambda: ("测试学期", 1, semester_start.isoformat()))
    data = client.get("/api/schedule/today").get_json()
    assert [item["title"] for item in data["timed"]] == ["自动控制", "实验", "组会"]
    assert data["deadlines"] == [{"title": "周度复盘", "course": "Python学习"}, {"title": "实验报告"}]
