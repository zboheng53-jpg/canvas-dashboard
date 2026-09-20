"""Shared test profiles, isolated data, deterministic browser time and failure evidence."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from datetime import datetime, timezone, timedelta

import pytest
from werkzeug.serving import make_server

# Isolation must precede app imports, which create the session secret.
_previous_data_root = os.environ.get("CANVAS_DASHBOARD_DATA_DIR")
_session_data = tempfile.TemporaryDirectory(prefix="canvas-dashboard-tests-")
os.environ["CANVAS_DASHBOARD_DATA_DIR"] = str(Path(_session_data.name) / "data")

import app as dashboard_app
import user_paths
import auth
import agent_auth
import apple_calendar
import haoke_client
import zhixuemeng_client
import zhihuishu_store
import zhihuishu_worker
import zhihuishu_login_sessions
import tongji_login_sessions

FIXED_NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def pytest_configure(config):
    config.addinivalue_line("markers", "now(iso): set the same local datetime in Flask and the browser")


@pytest.fixture
def test_now(request):
    marker = request.node.get_closest_marker("now")
    return datetime.fromisoformat(marker.args[0]) if marker else FIXED_NOW


def pytest_addoption(parser):
    parser.addoption("--suite", choices=("all", "quick", "acceptance"), default="all")


def pytest_collection_modifyitems(config, items):
    suite = config.getoption("--suite")
    safety = {"test_p0_safety.py", "test_security_auth.py", "test_action_workspace.py",
              "test_account_lifecycle.py", "test_project_focus.py", "test_concurrent_writes.py", "test_scripts.py",
              "test_development_workflow.py", "test_deploy_configs.py",
              "test_control_components.py", "test_design_system_lint.py", "test_css_architecture.py",
              "test_frontend_text_integrity.py", "test_dashboard_localization.py",
              "test_ui_refactor.py", "test_business_components.py"}
    selected, deselected = [], []
    for item in items:
        browser_test = "browser" in item.fixturenames
        include = (suite == "all" or (suite == "quick" and not browser_test)
                   or (suite == "acceptance" and (browser_test or item.path.name in safety)))
        (selected if include else deselected).append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)


def pytest_unconfigure(config):
    if _previous_data_root is None:
        os.environ.pop("CANVAS_DASHBOARD_DATA_DIR", None)
    else:
        os.environ["CANVAS_DASHBOARD_DATA_DIR"] = _previous_data_root
    _session_data.cleanup()


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    for module in (dashboard_app, user_paths, auth, agent_auth, apple_calendar,
                   haoke_client, zhixuemeng_client, zhihuishu_store,
                   zhihuishu_login_sessions, tongji_login_sessions):
        monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    for name, filename in (("USERS_FILE", "users.json"), ("SECRET_KEY_FILE", ".flask_secret_key"),
                           ("DELETION_LEDGER_FILE", ".account_deletion_ledger.json"),
                           ("ADMIN_AUDIT_FILE", "account_admin_audit.json")):
        monkeypatch.setattr(auth, name, tmp_path / filename)
    for module in (haoke_client, zhixuemeng_client):
        monkeypatch.setattr(module, "KEY_FILE", tmp_path / ".encryption_key")
    monkeypatch.setattr(zhihuishu_worker, "LOCK_FILE", tmp_path / "zhihuishu_worker.lock")
    monkeypatch.setattr(dashboard_app, "_TERM_CONFIG_FILE", tmp_path / "term_config.json")
    monkeypatch.setattr(dashboard_app, "_HOLIDAY_CACHE_FILE", tmp_path / "holiday_cache.json")
    return tmp_path


@pytest.fixture
def live_app(isolated_data, monkeypatch, test_now):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return test_now.astimezone(tz) if tz else test_now.replace(tzinfo=None)

    monkeypatch.setattr(dashboard_app, "datetime", FixedDateTime)
    dashboard_app._rate_limit_buckets.clear()
    monkeypatch.setattr(dashboard_app, "_get_holidays", lambda: [])
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
    monkeypatch.setitem(dashboard_app.app.config, "TESTING", True)
    server = make_server("127.0.0.1", 0, dashboard_app.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, "report_" + report.when, report)


@pytest.fixture(scope="session")
def chromium():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def browser(chromium, request, test_now):
    # Keep existing browser.new_page/new_context callers while sharing one launch.
    contexts = []
    errors = []

    class TestBrowser:
        def new_context(self, **kwargs):
            kwargs.setdefault("timezone_id", "Asia/Shanghai")
            context = chromium.new_context(**kwargs)
            context.add_init_script("""(() => {
                const RealDate = Date;
                const now = %d;
                window.Date = class extends RealDate {
                    constructor(...args) { super(...(args.length ? args : [now])); }
                    static now() { return now; }
                };
            })();""" % int(test_now.timestamp() * 1000))
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            def observe(page):
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            context.on("page", observe)
            contexts.append(context)
            return context

        def new_page(self, **kwargs):
            return self.new_context(**kwargs).new_page()

    yield TestBrowser()
    report = getattr(request.node, "report_call", None)
    failed = report is not None and report.failed
    folder = Path(os.environ.get("CANVAS_TEST_ARTIFACTS", "test-results/direct")) / hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:16]
    if failed:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "failure.json").write_text(json.dumps({"test": request.node.nodeid, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    for index, context in enumerate(contexts):
        try:
            if failed:
                for number, page in enumerate(context.pages):
                    if not page.is_closed():
                        page.screenshot(path=str(folder / f"page-{index}-{number}.png"), timeout=5000)
                context.tracing.stop(path=str(folder / f"trace-{index}.zip"))
            else:
                context.tracing.stop()
        except Exception as error:
            if failed:
                (folder / f"capture-{index}.txt").write_text(str(error), encoding="utf-8")
        finally:
            context.close()
