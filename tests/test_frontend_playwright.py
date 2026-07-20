import json
import re
import threading
from datetime import datetime

import pytest
from werkzeug.serving import make_server

import app as dashboard_app
import user_paths

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 9, 12, 0, tzinfo=dashboard_app.CST)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


@pytest.fixture
def live_app(tmp_path, monkeypatch):
    user_root = tmp_path / "users"

    def resolve_user_dir(username):
        path = user_root / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "user_dir", resolve_user_dir)
    monkeypatch.setattr(dashboard_app.auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app.auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(dashboard_app.auth, "SECRET_KEY_FILE", tmp_path / ".flask_secret_key")
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "datetime", FixedDateTime)
    if hasattr(dashboard_app, "_rate_limit_buckets"):
        dashboard_app._rate_limit_buckets.clear()

    class WeatherResponse:
        def json(self):
            return {
                "current": {
                    "temperature_2m": 26,
                    "relative_humidity_2m": 55,
                    "weather_code": 0,
                    "wind_speed_10m": 8,
                }
            }

    monkeypatch.setattr(dashboard_app.requests, "get", lambda *args, **kwargs: WeatherResponse())
    monkeypatch.setattr(
        dashboard_app,
        "fetch_canvas_planner",
        lambda username: {
            "ok": True,
            "data": [
                {
                    "id": 101,
                    "title": "Canvas seeded",
                    "course": "Canvas",
                    "due_str": "07-10",
                    "due_ts": "2099-07-10T00:00:00+08:00",
                    "type": "Canvas",
                    "url": "",
                }
            ],
            "cached": False,
        },
    )
    monkeypatch.setattr(dashboard_app, "load_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    monkeypatch.setattr(dashboard_app, "save_state", lambda username, state: None)
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: {"ok": True, "data": [], "cached": False})
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    monkeypatch.setattr(dashboard_app, "save_haoke_state", lambda username, state: None)
    monkeypatch.setattr(dashboard_app, "fetch_zxm_assignments", lambda username, course_code=None: {"ok": True, "items": [], "cached": False})
    monkeypatch.setattr(dashboard_app, "load_zxm_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    monkeypatch.setattr(dashboard_app, "save_zxm_state", lambda username, state: None)
    monkeypatch.setattr(dashboard_app, "get_selected_course", lambda username: None)
    monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_status", lambda username: {"session": "ok"})
    monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    monkeypatch.setattr(
        dashboard_app.zhihuishu_store,
        "load_cache",
        lambda username: {"items": [], "stale": False, "fetched_at": None},
    )
    monkeypatch.setattr(dashboard_app.zhihuishu_login_sessions, "load_session", lambda username: None)
    dashboard_app.app.config.update(TESTING=True)
    server = make_server("127.0.0.1", 0, dashboard_app.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


def register_dashboard_user(page, live_app, username):
    page.goto(f"{live_app}/register")
    page.fill("#register-username", username)
    page.fill("#register-password", "strong-password")
    page.click("#register-form button")
    page.wait_for_url(f"{live_app}/")


def test_frontend_new_todo_date_defaults_to_server_today(live_app, browser):
    page = browser.new_page()
    register_dashboard_user(page, live_app, "dateuser")

    expect(page.locator("#new-todo-due")).to_have_value("2026-07-09")
    expect(page.locator("#new-todo-due")).to_have_attribute("aria-label", "截止日期")


def test_frontend_todo_heading_is_centered_in_header(live_app, browser):
    page = browser.new_page()
    register_dashboard_user(page, live_app, "headinguser")

    header_box = page.locator(".section-header").bounding_box()
    title_box = page.locator(".section-header h2").bounding_box()
    assert header_box is not None
    assert title_box is not None

    header_center = header_box["y"] + header_box["height"] / 2
    title_center = title_box["y"] + title_box["height"] / 2
    assert abs(header_center - title_center) <= 8


@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_header_shows_compact_weather_and_term(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"mobileheader{width}")

    weather_desc = page.locator(".weather-desc")
    weather_detail = page.locator(".weather-detail")
    term_info = page.locator("#term-info")
    expect(weather_desc).to_be_visible()
    expect(weather_detail).to_be_visible()
    expect(weather_detail).to_contain_text("湿度 55%")
    expect(weather_detail).to_contain_text("风速 8 m/s")
    expect(term_info).to_be_visible()

    emoji_box = page.locator(".weather-emoji").bounding_box()
    temp_box = page.locator(".weather-temp").bounding_box()
    desc_box = weather_desc.bounding_box()
    detail_box = weather_detail.bounding_box()
    term_box = term_info.bounding_box()
    assert all(box is not None for box in (emoji_box, temp_box, desc_box, detail_box, term_box))
    assert emoji_box["x"] < temp_box["x"]
    assert abs((emoji_box["y"] + emoji_box["height"] / 2) - (temp_box["y"] + temp_box["height"] / 2)) <= 3
    assert desc_box["y"] > temp_box["y"]
    assert abs((desc_box["y"] + desc_box["height"] / 2) - (detail_box["y"] + detail_box["height"] / 2)) <= 2
    assert term_box["y"] >= max(
        desc_box["y"] + desc_box["height"],
        detail_box["y"] + detail_box["height"],
    )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_frontend_desktop_header_keeps_weather_and_term_layout(live_app, browser):
    page = browser.new_page(viewport={"width": 769, "height": 844})
    register_dashboard_user(page, live_app, "desktopheader")

    expect(page.locator(".weather-desc")).to_be_visible()
    expect(page.locator(".weather-detail")).to_be_visible()
    expect(page.locator("#term-info")).to_be_visible()
    assert page.locator(".weather-card").evaluate(
        "element => getComputedStyle(element).flexDirection"
    ) == "row"
    assert page.locator(".header-summary").evaluate(
        "element => getComputedStyle(element).display"
    ) == "grid"
    assert page.locator(".clock-section .time").evaluate(
        "element => getComputedStyle(element).fontSize"
    ) == "62px"


def test_frontend_titles_use_relaxed_serif_style(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "seriftitles")

    for selector, expected_letter_spacing in (
        (".section-header h2", "-1.12px"),
        ("#long-term-projects-title", "-0.8px"),
        ("#today-schedule-title", "-0.8px"),
    ):
        style = page.locator(selector).evaluate(
            "element => { const style = getComputedStyle(element); return { fontFamily: style.fontFamily, fontWeight: style.fontWeight, letterSpacing: style.letterSpacing }; }"
        )
        assert "Noto Serif SC" in style["fontFamily"]
        assert style["fontWeight"] == "500"
        assert style["letterSpacing"] == expected_letter_spacing


def test_frontend_todo_hover_keeps_content_and_actions_in_place(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "todohovers")

    todo = page.locator("#todo-list .unified-item").first
    title = todo.locator(".item-title")
    dismiss_button = todo.locator(".item-desktop-actions .btn-dismiss")
    title_before = title.bounding_box()
    dismiss_before = dismiss_button.bounding_box()
    assert title_before is not None
    assert dismiss_before is not None

    todo.hover()

    title_after = title.bounding_box()
    dismiss_after = dismiss_button.bounding_box()
    assert title_after is not None
    assert dismiss_after is not None
    assert title_after["x"] == pytest.approx(title_before["x"], abs=1)
    assert dismiss_after["x"] == pytest.approx(dismiss_before["x"], abs=1)


def test_frontend_v2_desktop_shell_uses_bounded_three_column_layout(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "desktopv2")

    sidebar = page.locator("#academic-sidebar")
    workspace = page.locator(".workspace-main")
    right_rail = page.locator("#dashboard-right-rail")
    expect(sidebar).to_be_visible()
    expect(workspace).to_be_visible()
    expect(right_rail).to_be_visible()

    sidebar_box = sidebar.bounding_box()
    workspace_box = workspace.bounding_box()
    right_box = right_rail.bounding_box()
    assert sidebar_box is not None
    assert workspace_box is not None
    assert right_box is not None
    assert 180 <= sidebar_box["width"] <= 200
    assert 820 <= workspace_box["width"] <= 860
    assert 320 <= right_box["width"] <= 360
    assert 20 <= workspace_box["x"] - (sidebar_box["x"] + sidebar_box["width"]) <= 24
    assert 20 <= right_box["x"] - (workspace_box["x"] + workspace_box["width"]) <= 24
    assert right_box["height"] == pytest.approx(sidebar_box["height"], abs=1)
    assert right_box["y"] + right_box["height"] == pytest.approx(
        sidebar_box["y"] + sidebar_box["height"],
        abs=1,
    )
    rail_cards = right_rail.locator(".rail-card")
    assert rail_cards.count() == 2
    first_rail_box = rail_cards.nth(0).bounding_box()
    second_rail_box = rail_cards.nth(1).bounding_box()
    assert first_rail_box is not None
    assert second_rail_box is not None
    assert first_rail_box["height"] == pytest.approx(second_rail_box["height"], abs=1)
    todo_card = page.locator(".workspace-main .enter-main-card")
    expect(todo_card).to_have_css(
        "transform", re.compile(r"matrix\(1, 0, 0, 1, 0, 0\)")
    )
    todo_card_box = todo_card.bounding_box()
    assert todo_card_box is not None
    assert todo_card_box["y"] + todo_card_box["height"] == pytest.approx(
        sidebar_box["y"] + sidebar_box["height"],
        abs=1,
    )

    collapse = page.locator("#sidebar-collapse-toggle")
    collapse.click()
    expect(collapse).to_have_attribute("aria-expanded", "false")
    collapsed_box = sidebar.bounding_box()
    assert collapsed_box is not None
    assert 64 <= collapsed_box["width"] <= 80
    expect(sidebar.locator(".sidebar-label").first).to_be_hidden()


def test_frontend_desktop_todo_card_scrolls_without_outgrowing_sidebars(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "todocardscroll")
    page.wait_for_timeout(1000)

    page.evaluate(
        """() => {
            document.getElementById('todo-list').innerHTML = Array.from(
                { length: 18 },
                (_, index) => `<div class="todo-item unified-item"><span class="item-title">Overflow todo ${index}</span></div>`
            ).join('');
        }"""
    )

    todo_card = page.locator(".workspace-main .enter-main-card")
    todo_list = page.locator("#todo-list")
    sidebar = page.locator("#academic-sidebar")
    expect(todo_list.locator(".unified-item")).to_have_count(18)
    expect(todo_card).to_have_css(
        "transform", re.compile(r"matrix\(1, 0, 0, 1, 0, 0\)")
    )

    todo_card_box = todo_card.bounding_box()
    sidebar_box = sidebar.bounding_box()
    assert todo_card_box is not None
    assert sidebar_box is not None
    assert todo_card_box["y"] + todo_card_box["height"] == pytest.approx(
        sidebar_box["y"] + sidebar_box["height"], abs=1
    )
    assert todo_list.evaluate("element => element.scrollHeight > element.clientHeight")
    assert todo_list.evaluate("element => getComputedStyle(element).overflowY") == "auto"


def test_frontend_v2_narrow_desktop_stacks_right_rail_below_center(live_app, browser):
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    register_dashboard_user(page, live_app, "narrowv2")

    sidebar = page.locator("#academic-sidebar")
    workspace = page.locator(".workspace-main")
    right_rail = page.locator("#dashboard-right-rail")
    sidebar_box = sidebar.bounding_box()
    workspace_box = workspace.bounding_box()
    right_box = right_rail.bounding_box()
    assert sidebar_box is not None
    assert workspace_box is not None
    assert right_box is not None
    assert 64 <= sidebar_box["width"] <= 80
    assert workspace_box["width"] <= 860
    assert right_box["x"] == pytest.approx(workspace_box["x"], abs=1)
    vertical_gap = right_box["y"] - (workspace_box["y"] + workspace_box["height"])
    assert 20 <= vertical_gap <= 24


def test_frontend_v2_sidebar_uses_light_reference_style(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "lightsidebarv2")

    styles = page.locator("#academic-sidebar").evaluate(
        """element => {
            const sidebar = getComputedStyle(element);
            const active = getComputedStyle(element.querySelector('.sidebar-nav-item.is-active'));
            const user = getComputedStyle(element.querySelector('.sidebar-user'));
            return {
                background: sidebar.backgroundColor,
                activeBackground: active.backgroundColor,
                activeColor: active.color,
                userBorder: user.borderTopWidth,
            };
        }"""
    )
    assert styles["background"] == "rgb(255, 255, 255)"
    assert styles["activeBackground"] != "rgba(0, 0, 0, 0)"
    assert styles["activeColor"] == "rgb(47, 107, 214)"
    assert styles["userBorder"] == "1px"


def test_frontend_console_navigation_groups_features_without_overview_duplicates(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    register_dashboard_user(page, live_app, "consolev2")

    expect(page.locator(".sidebar-nav-group")).to_have_count(3)
    expect(page.locator(".sidebar-section-label")).to_have_text(["工作区", "计划", "管理"])
    expect(page.locator("[data-dashboard-view] .sidebar-label")).to_have_text(
        ["今日总览", "长期项目", "日程与课表", "连接与同步", "Apple Calendar", "偏好设置"]
    )
    expect(page.locator("#dashboard-view-overview .login-trigger")).to_have_count(0)
    expect(page.locator("#dashboard-view-overview .account-row")).to_have_count(0)
    expect(page.locator("#dashboard-view-overview #login-cards")).to_have_count(0)

    page.locator('[data-dashboard-view="connections"]').click()
    expect(page.locator("#dashboard-view-connections")).to_be_visible()
    expect(page.locator("#dashboard-view-connections #login-cards")).to_be_visible()
    expect(page.locator("#dashboard-view-connections .login-card")).to_have_count(4)

    page.locator('[data-dashboard-view="schedule"]').click()
    expect(page.locator("#dashboard-view-schedule")).to_be_visible()
    expect(page.locator("#schedule-timetable-grid")).to_be_visible()
    expect(page.locator("#schedule-week-label")).to_be_visible()

    for view_name in ("overview", "projects", "schedule", "connections", "calendar", "settings"):
        button = page.locator(f'[data-dashboard-view="{view_name}"]')
        button.click()
        expect(page.locator(f'[data-view-panel="{view_name}"]')).to_be_visible()
        expect(page.locator(".sidebar-nav-item.is-active")).to_have_count(1)
        expect(button).to_have_attribute("aria-current", "page")
        if view_name == "overview":
            expect(page.locator("#dashboard-right-rail")).to_be_visible()
        else:
            expect(page.locator("#dashboard-right-rail")).to_be_hidden()
    page.locator(".sidebar-user").click()
    expect(page.locator("#dashboard-view-settings")).to_be_visible()
    assert page_errors == []


@pytest.mark.parametrize(("width", "height"), [(1024, 844), (1440, 1000)])
def test_frontend_connections_use_two_equal_full_height_cards(live_app, browser, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    register_dashboard_user(page, live_app, "connectioncards")
    page.locator('[data-dashboard-view="connections"]').click()
    expect(page.locator("#dashboard-view-connections")).to_be_visible()

    panel_styles = page.evaluate(
        """() => {
            const read = selector => {
                const style = getComputedStyle(document.querySelector(selector));
                return {
                    background: style.backgroundColor,
                    radius: parseFloat(style.borderTopLeftRadius),
                };
            };
            return {
                list: read('.connections-list-panel'),
                detail: read('.connections-detail-panel'),
                content: read('.detail-content-box'),
            };
        }"""
    )
    assert panel_styles["list"]["background"] == "rgb(255, 255, 255)"
    assert panel_styles["detail"]["background"] == "rgb(255, 255, 255)"
    assert panel_styles["content"]["background"] == "rgb(248, 251, 255)"
    assert panel_styles["list"]["radius"] >= 10
    assert panel_styles["detail"]["radius"] >= 10

    measurements = []
    for platform in ("canvas", "haoke", "zhixuemeng", "zhihuishu"):
        card = page.locator(f'#login-cards .login-card[data-platform="{platform}"]')
        card.click()
        expect(card).to_have_class(re.compile(r"\bis-selected\b"))
        expect(page.locator(f"#detail-{platform}")).to_be_visible()
        measurements.append(
            page.evaluate(
                """() => {
                    const rect = selector => {
                        const box = document.querySelector(selector).getBoundingClientRect();
                        return {
                            x: box.x,
                            y: box.y,
                            width: box.width,
                            height: box.height,
                            right: box.right,
                            bottom: box.bottom,
                        };
                    };
                    return {
                        manager: rect('.connections-manager-card'),
                        list: rect('.connections-list-panel'),
                        detail: rect('.connections-detail-panel'),
                    };
                }"""
            )
        )
    first_detail = measurements[0]["detail"]
    for measurement in measurements:
        list_box = measurement["list"]
        detail_box = measurement["detail"]
        assert detail_box["x"] - list_box["right"] == pytest.approx(20, abs=1)
        assert list_box["height"] == pytest.approx(detail_box["height"], abs=1)
        assert measurement["manager"]["bottom"] - detail_box["bottom"] <= 30
        assert detail_box["x"] == pytest.approx(first_detail["x"], abs=1)
        assert detail_box["y"] == pytest.approx(first_detail["y"], abs=1)
        assert detail_box["width"] == pytest.approx(first_detail["width"], abs=1)
        assert detail_box["height"] == pytest.approx(first_detail["height"], abs=1)


def test_frontend_v2_sidebar_greeting_and_calendar_subscription_page(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "calendarv2")

    expect(page.locator("#sidebar-greeting")).to_have_text(re.compile(r"^(早上好|上午好|中午好|下午好|晚上好|夜深了)，calendarv2$"))
    expect(page.locator(".sidebar-brand-copy small")).to_have_count(0)
    page.locator('[data-dashboard-view="calendar"]').click()
    expect(page.locator("#dashboard-view-calendar")).to_be_visible()
    expect(page.locator("#calendar-subscription-card")).to_be_visible()
    expect(page.locator("#calendar-subscription-panel")).to_have_count(0)
    expect(page.locator("#calendar-subscription-title")).to_have_text("Apple Calendar 订阅")
    expect(page.locator("#calendar-subscription-open")).to_be_disabled()
    assert page.locator("#calendar-subscription-create").evaluate(
        "element => getComputedStyle(element).backgroundColor"
    ) == "rgb(47, 107, 214)"
    page.locator("#calendar-subscription-create").click()
    expect(page.locator("#calendar-subscription-url")).to_have_value(re.compile(r"/calendar/.+\.ics$"))
    expect(page.locator("#calendar-subscription-open")).to_be_enabled()
    page.locator("#calendar-subscription-revoke").click()
    expect(page.locator("#calendar-subscription-status")).to_have_text("日历订阅已撤销")


def test_frontend_hides_calendar_view_when_feature_is_disabled(live_app, browser, monkeypatch):
    monkeypatch.setattr(dashboard_app.settings, "APPLE_CALENDAR_ENABLED", False)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "calendaroffv2")

    expect(page.locator('[data-dashboard-view="calendar"]')).to_have_count(0)
    expect(page.locator("#dashboard-view-calendar")).to_have_count(0)


def test_frontend_source_filters_and_focus_views(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "groupingv2")

    source_filters = page.locator("[data-todo-source]")
    expect(source_filters).to_have_count(6)
    expect(page.locator('[data-todo-source="all"]')).to_have_text("全部 (1)")
    expect(page.locator('[data-todo-source="canvas"]')).to_have_text("Canvas (1)")
    expect(page.locator('[data-todo-source="custom"]')).to_have_text("自定义 (0)")
    expect(page.locator(".todo-group-heading").first).to_contain_text("之后")
    page.fill("#new-todo-input", "Tag grouping task #automation")
    page.fill("#new-todo-due", "2026-07-16")
    page.click("#add-todo-form button")
    expect(page.locator(".todo-group-heading").filter(has_text="本周安排")).to_be_visible()
    page.locator('[data-todo-source="custom"]').click()
    expect(page.locator('[data-todo-source="custom"]')).to_have_text("自定义 (1)")
    expect(page.locator(".unified-item").filter(has_text="Tag grouping task")).to_be_visible()
    expect(page.locator(".unified-item").filter(has_text="Canvas seeded")).to_have_count(0)

    overview_width = page.locator(".workspace-main").bounding_box()["width"]
    page.locator('[data-dashboard-view="projects"]').click()
    projects_width = page.locator(".workspace-main").bounding_box()["width"]
    expect(page.locator("#dashboard-view-projects")).to_be_visible()
    assert projects_width > overview_width + 300

    page.locator('[data-dashboard-view="schedule"]').click()
    expect(page.locator("#dashboard-view-schedule")).to_be_visible()
    schedule_box = page.locator(".schedule-manager-card").bounding_box()
    assert schedule_box is not None and schedule_box["width"] > 800


def test_frontend_v2_mobile_menu_placeholders_and_stacked_modules(live_app, browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    register_dashboard_user(page, live_app, "mobilev2")

    menu = page.locator("#mobile-menu-toggle")
    sidebar = page.locator("#academic-sidebar")
    expect(menu).to_be_visible()
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(sidebar).to_have_attribute("aria-hidden", "true")

    project_card = page.locator("#long-term-projects-card")
    schedule_card = page.locator("#today-schedule-card")
    project_box = project_card.bounding_box()
    schedule_box = schedule_card.bounding_box()
    workspace_box = page.locator(".workspace-main").bounding_box()
    assert project_box is not None
    assert schedule_box is not None
    assert workspace_box is not None
    assert project_box["y"] >= workspace_box["y"] + workspace_box["height"]
    assert schedule_box["y"] > project_box["y"] + project_box["height"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "true")
    expect(sidebar).to_have_attribute("aria-hidden", "false")
    page.locator('[data-dashboard-view="projects"]').click()
    expect(page.locator("#dashboard-view-projects")).to_be_visible()
    expect(page.locator("#dashboard-view-overview")).to_be_hidden()
    expect(page.locator("#dashboard-right-rail")).to_be_hidden()
    expect(menu).to_have_attribute("aria-expanded", "false")


def test_frontend_schedule_management_renders_today_busy_item(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "schedulev2")
    expect(page.locator("#today-schedule-content")).to_have_attribute("aria-busy", "false")
    page.locator('[data-dashboard-view="schedule"]').click()
    expect(page.locator("#dashboard-view-schedule")).to_be_visible()
    expect(page.locator("#schedule-week-label")).to_contain_text("2026年7月6日 - 7月12日")
    page.click("#btn-add-schedule-item")
    expect(page.locator("#schedule-item-modal")).to_be_visible()
    page.check('#schedule-modal-form input[value="one-off"]')
    page.fill('#schedule-modal-form [name="title"]', "实验室值班")
    page.fill('#schedule-modal-form [name="date"]', "2026-07-09")
    page.fill('#schedule-modal-form [name="start_time"]', "18:00")
    page.fill('#schedule-modal-form [name="end_time"]', "19:00")
    page.click('#schedule-modal-form .btn-submit')
    expect(page.locator("#schedule-timetable-grid")).to_contain_text("实验室值班")
    page.click('.schedule-nav-btn:has-text("上一周")')
    expect(page.locator("#schedule-week-label")).to_contain_text("2026年6月29日 - 7月5日")
    expect(page.locator("#schedule-timetable-grid")).not_to_contain_text("实验室值班")
    page.click('.schedule-nav-btn:has-text("下一周")')
    expect(page.locator("#schedule-week-label")).to_contain_text("2026年7月6日 - 7月12日")
    expect(page.locator("#schedule-timetable-grid")).to_contain_text("实验室值班")
    page.locator('[data-dashboard-view="overview"]').click()
    expect(page.locator("#today-schedule-content")).to_contain_text("实验室值班")


def test_frontend_projects_overview_limits_cards_and_opens_manager(live_app, browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    project_requests = []
    page.on(
        "request",
        lambda request: project_requests.append(request.url)
        if request.url.endswith("/api/projects")
        else None,
    )
    register_dashboard_user(page, live_app, "projectsv2")
    expect(page.locator("#project-overview-content")).to_contain_text("暂无长期项目")
    page.locator("#project-empty-create").click()
    expect(page.locator("#dashboard-view-projects")).to_be_visible()
    expect(page.locator("#project-composer")).to_be_visible()
    assert len(project_requests) == 1
    page.fill('#project-composer [name="name"]', "毕业设计")
    page.locator("#project-composer button").click()
    expect(page.locator("#project-manager-list")).to_contain_text("毕业设计")
    page.route(
        "**/api/projects/*",
        lambda route: route.abort()
        if route.request.method == "PUT"
        else route.continue_(),
    )
    page.fill('.project-edit-form [name="name"]', "保留的项目名称")
    page.locator(".project-edit-form button").click()
    expect(page.locator('#project-detail [name="name"]')).to_have_value("保留的项目名称")
    expect(page.locator("#project-manager-status")).to_contain_text("保存失败")


def test_frontend_right_rail_distinguishes_loading_failures_from_empty_states(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.route(
        "**/api/projects/overview",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"ok":false,"error":"unavailable"}',
        ),
    )
    page.route(
        "**/api/schedule/today",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"ok":false,"error":"unavailable"}',
        ),
    )

    register_dashboard_user(page, live_app, "railerrorsv2")

    expect(page.locator("#project-overview-content")).to_contain_text("长期项目加载失败")
    expect(page.locator("#today-schedule-content")).to_contain_text("今日日程加载失败")


@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_alignment_places_controls_on_the_right(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"alignment{width}")
    page.fill("#new-todo-input", "Alignment task #label")
    page.click("#add-todo-form button")

    item = page.locator(".unified-item-wrap").filter(has_text="Alignment task")
    expect(item).to_be_visible()
    label_box = item.locator(".item-labels").bounding_box()
    subtask_box = item.locator(".item-subtask-slot").bounding_box()
    heading_box = page.locator(".section-header h2").bounding_box()
    header_box = page.locator(".section-header").bounding_box()
    emoji_box = page.locator(".weather-emoji").bounding_box()
    temp_box = page.locator(".weather-temp").bounding_box()
    assert label_box is not None and subtask_box is not None
    assert heading_box is not None and header_box is not None
    assert emoji_box is not None and temp_box is not None
    assert subtask_box["x"] > label_box["x"]
    assert abs((heading_box["y"] + heading_box["height"] / 2) - (header_box["y"] + header_box["height"] / 2)) <= 8
    assert emoji_box["x"] < temp_box["x"]
    assert abs((emoji_box["y"] + emoji_box["height"] / 2) - (temp_box["y"] + temp_box["height"] / 2)) <= 2


@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_todo_layout_is_compact_and_tappable(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"mobiletodo{width}")

    todo = page.locator(".unified-item").first
    expect(todo).to_be_visible()
    assert todo.evaluate("element => getComputedStyle(element).display") == "grid"
    assert page.evaluate("document.documentElement.scrollWidth") <= width

    todo_input_box = page.locator("#new-todo-input").bounding_box()
    date_input_box = page.locator("#new-todo-due").bounding_box()
    add_button_box = page.locator("#add-todo-form button").bounding_box()
    assert todo_input_box is not None
    assert date_input_box is not None
    assert add_button_box is not None
    assert abs(todo_input_box["y"] - date_input_box["y"]) < 1
    assert abs(todo_input_box["y"] - add_button_box["y"]) < 1
    expect(todo.locator(".item-course")).to_be_hidden()

    trigger = todo.locator(".mobile-action-trigger")
    expect(trigger).to_be_visible()
    trigger_box = trigger.bounding_box()
    assert trigger_box is not None
    assert trigger_box["width"] >= 35.9
    assert trigger_box["height"] >= 35.9
    trigger.click()

    mobile_actions = todo.locator(".item-mobile-actions")
    expect(mobile_actions).to_be_visible()
    for selector, handler_name in (
        (".btn-flag", "toggleHighlight"),
        (".btn-dismiss", "toggleHide"),
        (".btn-delete", "toggleCanvasDelete"),
    ):
        button = mobile_actions.locator(selector)
        button_box = button.bounding_box()
        assert button_box is not None
        assert button_box["width"] >= 35.9
        assert button_box["height"] >= 35.9
        onclick = button.get_attribute("onclick")
        assert onclick is not None
        assert handler_name in onclick

    page.fill("#new-todo-input", "Mobile labels #lab")
    page.click("#add-todo-form button")
    custom_item = page.locator(".unified-item-wrap").filter(has_text="Mobile labels")
    expect(custom_item).to_be_visible()
    expect(custom_item.locator(".label-badge")).to_be_visible()
    expect(custom_item.locator(".subtask-toggle")).to_be_visible()
    subtask_toggle_box = custom_item.locator(".subtask-toggle").bounding_box()
    assert subtask_toggle_box is not None
    assert subtask_toggle_box["width"] >= 35.9
    assert subtask_toggle_box["height"] >= 35.9

    long_label = "x" * 240
    page.fill("#new-todo-input", f"Mobile long label #{long_label}")
    page.click("#add-todo-form button")
    long_label_item = page.locator(".unified-item-wrap").filter(has_text="Mobile long label")
    expect(long_label_item.locator(".label-badge")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= width

    page.click("#mobile-menu-toggle")
    page.click('[data-dashboard-view="connections"]')
    login_cards = page.locator("#login-cards")
    expect(login_cards).to_be_visible()
    expected_columns = 1 if width < 480 else 2
    assert len(login_cards.evaluate("element => getComputedStyle(element).gridTemplateColumns").split()) == expected_columns


@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_compact_controls_and_action_menu(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"compact{width}")

    expect(page.locator(".term-info")).to_be_visible()
    form_box = page.locator("#add-todo-form").bounding_box()
    title_box = page.locator("#new-todo-input").bounding_box()
    date_box = page.locator("#new-todo-due").bounding_box()
    add_box = page.locator("#add-todo-form button").bounding_box()
    assert form_box is not None
    assert title_box is not None
    assert date_box is not None
    assert add_box is not None
    assert abs(title_box["y"] - date_box["y"]) < 1
    assert abs(title_box["y"] - add_box["y"]) < 1
    assert page.evaluate("document.documentElement.scrollWidth") <= width

    items = page.locator(".unified-item")
    expect(items).to_have_count(1)
    first_item = items.nth(0)
    first_trigger = first_item.locator(".mobile-action-trigger")
    expect(first_trigger).to_be_visible()
    expect(first_trigger).to_have_attribute("aria-expanded", "false")
    expect(first_item.locator(".item-mobile-actions")).to_be_hidden()
    expect(first_item.locator(".item-desktop-actions")).to_be_hidden()

    first_trigger.click()
    expect(first_trigger).to_have_attribute("aria-expanded", "true")
    expect(first_item.locator(".item-mobile-actions")).to_be_visible()
    expect(first_item.locator(".item-mobile-actions .btn-flag")).to_be_visible()
    expect(first_item.locator(".item-mobile-actions .btn-dismiss")).to_be_visible()
    expect(first_item.locator(".item-mobile-actions .btn-delete")).to_be_visible()

    first_trigger.click()
    expect(first_trigger).to_have_attribute("aria-expanded", "false")
    expect(first_item.locator(".item-mobile-actions")).to_be_hidden()

    page.fill("#new-todo-input", "Second compact mobile todo")
    page.click("#add-todo-form button")
    expect(items).to_have_count(2)
    first_item = items.nth(0)
    second_item = items.nth(1)
    first_trigger = first_item.locator(".mobile-action-trigger")
    second_trigger = second_item.locator(".mobile-action-trigger")

    first_trigger.click()
    expect(first_item.locator(".item-mobile-actions")).to_be_visible()
    second_trigger.click()
    expect(first_item.locator(".item-mobile-actions")).to_be_hidden()
    expect(second_item.locator(".item-mobile-actions")).to_be_visible()


@pytest.mark.parametrize("width", [769, 1024])
def test_frontend_desktop_keeps_inline_todo_actions(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"desktopactions{width}")

    todo = page.locator(".unified-item")
    expect(todo.locator(".item-desktop-actions")).to_be_visible()
    expect(todo.locator(".mobile-action-trigger")).to_be_hidden()
    expect(todo.locator(".item-mobile-actions")).to_be_hidden()


def test_frontend_custom_todos_subtasks_platform_cards_without_ocr(live_app, browser):
    page = browser.new_page()
    register_dashboard_user(page, live_app, "alice")

    expect(page.locator("#card-status-canvas")).to_have_class(re.compile(r"\bconnected\b"))
    expect(page.locator("#card-status-haoke")).to_have_class(re.compile(r"\bconnected\b"))
    expect(page.locator("#card-status-zhixuemeng")).to_have_class(re.compile(r"\bconnected\b"))
    expect(page.locator("#card-status-zhihuishu")).to_have_class(re.compile(r"\bconnected\b"))

    page.fill("#new-todo-input", "Frontend task #lab #urgent")
    page.click("#add-todo-form button")
    custom_item = page.locator(".unified-item-wrap").filter(has_text="Frontend task")
    expect(custom_item).to_be_visible()
    expect(custom_item.locator(".item-source-badge")).to_have_text("\u81ea\u5b9a\u4e49")
    expect(custom_item.locator(".label-badge")).to_have_text(["lab", "urgent"])
    expect(custom_item.locator(".subtask-toggle")).to_have_text("\u25b8")

    custom_item.locator(".subtask-toggle").click()
    expect(custom_item.locator(".subtask-toggle")).to_have_text("\u25be")
    page.fill(".subtask-add-input", "Read chapter")
    page.press(".subtask-add-input", "Enter")
    expect(custom_item.locator(".subtask-text")).to_have_text("Read chapter")
    page.evaluate("window.customToday = '2026-07-09'")
    custom_item.locator(".subtask-due-input").fill("2026-07-09")
    custom_item.locator(".subtask-toggle").click()
    expect(custom_item.locator(".subtask-toggle")).to_have_text("\u25b8")
    expect(custom_item.locator(".subtask-upcoming-preview")).to_have_count(0)

    expect(page.locator(".ocr-trigger-arrow-btn")).to_have_count(0)
    expect(page.locator("#ocr-text-input")).to_have_count(0)


def test_frontend_v2_preserves_core_todo_actions(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    register_dashboard_user(page, live_app, "coreactionsv2")

    canvas_item = page.locator(".unified-item").filter(has_text="Canvas seeded")
    expect(canvas_item).to_be_visible()
    canvas_item.locator(".item-desktop-actions .btn-flag").click()
    expect(canvas_item).to_have_class(re.compile(r"\bmanual-flagged\b"))
    canvas_item.locator(".item-desktop-actions .btn-dismiss").click()
    expect(canvas_item).to_have_class(re.compile(r"\bdismissed\b"))
    expect(page.locator("#stat-total")).to_have_text("0")
    canvas_item.locator(".item-desktop-actions .btn-delete").click()
    expect(canvas_item).to_have_count(0)

    page.fill("#new-todo-input", "Original custom todo #lab")
    page.click("#add-todo-form button")
    custom_item = page.locator(".unified-item-wrap").filter(has_text="Original custom todo")
    expect(custom_item).to_be_visible()
    custom_item.locator(".editable-title").click()
    page.locator(".inline-edit-input").fill("Edited custom todo #updated")
    page.locator(".inline-edit-input").blur()

    custom_item = page.locator(".unified-item-wrap").filter(has_text="Edited custom todo")
    expect(custom_item.locator(".label-badge")).to_have_text("updated")
    custom_item.locator(".subtask-toggle").click()
    custom_item.locator(".subtask-add-input").fill("Preserved subtask")
    custom_item.locator(".subtask-add-input").press("Enter")
    expect(custom_item.locator(".subtask-text")).to_have_text("Preserved subtask")

    custom_item.locator(".item-desktop-actions .btn-dismiss").click()
    expect(custom_item.locator(".unified-item")).to_have_class(re.compile(r"\bdismissed\b"))
    custom_item.locator(".item-desktop-actions .btn-dismiss").click()
    expect(custom_item.locator(".unified-item")).not_to_have_class(re.compile(r"\bdismissed\b"))
    custom_item.locator(".item-desktop-actions .btn-delete").click()
    expect(custom_item).to_have_count(0)
