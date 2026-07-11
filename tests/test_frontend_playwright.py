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
    term_refresh = page.locator(".term-refresh-btn")
    expect(weather_desc).to_be_visible()
    expect(weather_detail).to_be_visible()
    expect(weather_detail).to_contain_text("湿度 55%")
    expect(weather_detail).to_contain_text("风速 8 m/s")
    expect(term_info).to_be_visible()
    expect(term_refresh).to_be_visible()

    emoji_box = page.locator(".weather-emoji").bounding_box()
    temp_box = page.locator(".weather-temp").bounding_box()
    desc_box = weather_desc.bounding_box()
    detail_box = weather_detail.bounding_box()
    term_box = term_info.bounding_box()
    assert all(box is not None for box in (emoji_box, temp_box, desc_box, detail_box, term_box))
    assert emoji_box["x"] < temp_box["x"]
    assert abs((emoji_box["y"] + emoji_box["height"] / 2) - (temp_box["y"] + temp_box["height"] / 2)) <= 2
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

    page.click(".login-trigger")
    login_cards = page.locator("#login-cards")
    expect(login_cards).to_be_visible()
    assert len(login_cards.evaluate("element => getComputedStyle(element).gridTemplateColumns").split()) == 2


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
