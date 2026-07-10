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
