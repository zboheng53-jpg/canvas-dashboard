
"""Shared test profiles, isolated data, deterministic browser time and failure evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from datetime import datetime, timezone, timedelta

import pytest
from werkzeug.serving import make_server

import browser_env

# Isolation must precede app imports, which create the session secret.
_previous_data_root = os.environ.get("CANVAS_DASHBOARD_DATA_DIR")
_session_data = tempfile.TemporaryDirectory(prefix="canvas-dashboard-tests-")
os.environ["CANVAS_DASHBOARD_DATA_DIR"] = str(Path(_session_data.name) / "data")

import app as dashboard_app
from routes import agent as agent_routes
from routes import planning as planning_routes
from services import workspace as workspace_service
from services import academic as academic_service
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
import ketangpai_client
import tongji_oj_client
import http_sync
import settings

FIXED_NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def pytest_configure(config):
    config.addinivalue_line("markers", "now(iso): set the same local datetime in Flask and the browser")
    config.addinivalue_line("markers", "waitress(threads): run live_app with the production WSGI server and optional thread count")


@pytest.fixture
def test_now(request):
    marker = request.node.get_closest_marker("now")
    return datetime.fromisoformat(marker.args[0]) if marker else FIXED_NOW


def pytest_addoption(parser):
    parser.addoption("--suite", choices=("all", "quick", "acceptance", "ui"), default="all")


def pytest_collection_modifyitems(config, items):
    suite = config.getoption("--suite")
    safety = {"test_p0_safety.py", "test_security_auth.py", "test_action_workspace.py",
              "test_account_lifecycle.py", "test_project_focus.py", "test_concurrent_writes.py", "test_scripts.py",
              "test_development_workflow.py", "test_deploy_configs.py", "test_login_capacity.py", "test_release_onboarding.py",
              "test_capacity_guard.py",
              "test_control_components.py", "test_design_system_lint.py", "test_css_architecture.py",
              "test_frontend_text_integrity.py", "test_dashboard_localization.py",
              "test_ui_refactor.py", "test_business_components.py", "test_prelaunch_foundations.py",
              "test_sync_remediation.py", "test_review_remediation_sync_edges.py", "test_review_remediation_accounts.py",
              "test_todo_deadlines.py"}
    # The ui suite is the fast loop for CSS/template/copy changes: browser interaction and layout
    # checks plus the cheap static frontend guards, without the account/storage/security gates.
    ui = {"test_design_system_lint.py", "test_css_architecture.py", "test_frontend_text_integrity.py",
          "test_dashboard_localization.py", "test_control_components.py", "test_component_lab.py"}
    selected, deselected = [], []
    for item in items:
        browser_test = "browser" in item.fixturenames
        ui_test = browser_test or item.path.name in ui
        include = (suite == "all" or (suite == "quick" and not browser_test)
                   or (suite == "acceptance" and (browser_test or item.path.name in safety))
                   or (suite == "ui" and ui_test))
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
                   zhihuishu_login_sessions, tongji_login_sessions,
                   ketangpai_client, tongji_oj_client, http_sync):
        monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    for name, filename in (("USERS_FILE", "users.json"), ("SECRET_KEY_FILE", ".flask_secret_key"),
                           ("DELETION_LEDGER_FILE", ".account_deletion_ledger.json"),
                           ("ADMIN_AUDIT_FILE", "account_admin_audit.json")):
        monkeypatch.setattr(auth, name, tmp_path / filename)
    for module in (haoke_client, zhixuemeng_client, ketangpai_client, tongji_oj_client):
        monkeypatch.setattr(module, "KEY_FILE", tmp_path / ".encryption_key")
    monkeypatch.setattr(zhihuishu_worker, "LOCK_FILE", tmp_path / "zhihuishu_worker.lock")
    monkeypatch.setattr(academic_service, "_TERM_CONFIG_FILE", tmp_path / "term_config.json")
    monkeypatch.setattr(academic_service, "_HOLIDAY_CACHE_FILE", tmp_path / "holiday_cache.json")
    return tmp_path


@pytest.fixture
def live_app(isolated_data, monkeypatch, test_now, request):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return test_now.astimezone(tz) if tz else test_now.replace(tzinfo=None)

    for module in (dashboard_app, academic_service, workspace_service, planning_routes, agent_routes):
        monkeypatch.setattr(module, "datetime", FixedDateTime)
    dashboard_app._rate_limit_buckets.clear()
    monkeypatch.setattr(academic_service, "_get_holidays", lambda: [])
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
        "get_canvas_cached_todos",
        lambda username: {
            "ok": True,
            "data": [
                {
                    "id": "canvas:assignment:101",
                    "title": "Canvas seeded",
                    "course": "Canvas",
                    "due_str": "07-10",
                    "due_ts": "2099-07-10T00:00:00+08:00",
                    "type": "Canvas",
                    "url": "",
                }
            ],
            "cached": True,
            "has_cache": True,
            "stale": False,
        },
    )
    monkeypatch.setattr(dashboard_app, 'has_feed_url', lambda username: True)
    # Completion refreshes the platform card from the server, so the shared
    # fixture must keep the local state writes the API actually commits;
    # otherwise the refresh response would report an empty state.
    canvas_state = {"hidden": [], "highlighted": [], "deleted": [], "completed": [], "overrides": {}}
    monkeypatch.setattr(dashboard_app, "load_state", lambda username: {
        key: list(value) if isinstance(value, list) else dict(value) for key, value in canvas_state.items()})
    monkeypatch.setattr(dashboard_app, "save_state", lambda username, state: canvas_state.update(state))

    def _update_canvas_state(username, action, item_id):
        """Mirror PlatformStateStore.update so a refresh observes the same state."""
        if action == "hide" and item_id not in canvas_state["hidden"]:
            canvas_state["hidden"].append(item_id)
        elif action == "unhide":
            canvas_state["hidden"] = [each for each in canvas_state["hidden"] if each != item_id]
        elif action == "highlight" and item_id not in canvas_state["highlighted"]:
            canvas_state["highlighted"].append(item_id)
        elif action == "unhighlight":
            canvas_state["highlighted"] = [each for each in canvas_state["highlighted"] if each != item_id]
        elif action == "delete" and item_id not in canvas_state["deleted"]:
            canvas_state["deleted"].append(item_id)
            canvas_state["hidden"] = [each for each in canvas_state["hidden"] if each != item_id]
            canvas_state["highlighted"] = [each for each in canvas_state["highlighted"] if each != item_id]
        elif action == "undelete":
            canvas_state["deleted"] = [each for each in canvas_state["deleted"] if each != item_id]
        elif action == "complete" and item_id not in canvas_state["completed"]:
            canvas_state["completed"].append(item_id)
        elif action == "uncomplete":
            canvas_state["completed"] = [each for each in canvas_state["completed"] if each != item_id]
        return {key: list(value) if isinstance(value, list) else dict(value) for key, value in canvas_state.items()}

    monkeypatch.setattr(dashboard_app, "update_state", _update_canvas_state)
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: {"ok": True, "data": [], "cached": False})
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: True)
    monkeypatch.setattr(dashboard_app, "get_haoke_cached_todos", lambda username: {
        "ok": True, "data": [], "cached": True, "has_cache": True, "stale": False,
    })
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: {"hidden": [], "highlighted": [], "deleted": []})
    monkeypatch.setattr(dashboard_app, "save_haoke_state", lambda username, state: None)
    monkeypatch.setattr(dashboard_app, "fetch_zxm_assignments", lambda username, course_code=None: {"ok": True, "items": [], "cached": False})
    import platform_http
    cached_assignments = platform_http.cached_assignments
    monkeypatch.setattr(platform_http, "cached_assignments", lambda username, platform, course=None:
        {"ok": True, "items": [], "courses": [], "cached": True, "has_cache": True,
         "need_setup": False, "stale": False, "sync_complete": True}
        if platform == "zhixuemeng" else cached_assignments(username, platform, course))
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
    waitress_marker = request.node.get_closest_marker("waitress")
    production_server = waitress_marker is not None
    if production_server:
        from waitress.server import create_server
        server_map = {}
        server = create_server(dashboard_app.app, host="127.0.0.1", port=0,
                               threads=waitress_marker.kwargs.get("threads", settings.APP_THREADS), map=server_map)
        port = server.effective_port
        run = server.run
    else:
        server = make_server("127.0.0.1", 0, dashboard_app.app, threaded=True)
        port = server.server_port
        run = server.serve_forever
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        if production_server:
            server.task_dispatcher.shutdown()
            for channel in list(server_map.values()):
                channel.close()
        else:
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


def _capture_failure_evidence(contexts, folder):
    """Save final DOM and screenshots for a failed browser test.

    Evidence is collected on failure only: tracing or response listeners on every test are both
    expensive and observable, and a listener attached to the page really did stop the dashboard
    from starting a background request in test_tongji_oj_browser. A finishing DOM dump keeps the
    failure debuggable without touching the running test.
    """
    captured = []
    for index, context in enumerate(contexts):
        for number, page in enumerate(context.pages):
            try:
                if page.is_closed():
                    continue
                page.screenshot(path=str(folder / f"page-{index}-{number}.png"), timeout=5000)
            except Exception as error:
                captured.append(f"page-{index}-{number}.png: {error}")
            try:
                (folder / f"dom-{index}-{number}.html").write_text(page.content(), encoding="utf-8")
            except Exception as error:
                captured.append(f"dom-{index}-{number}.html: {error}")
    return captured


@pytest.fixture
def browser(chromium, request, test_now):
    # Keep existing browser.new_page/new_context callers while sharing one launch.
    contexts = []
    errors = []

    class TestBrowser:
        def new_context(self, **kwargs):
            kwargs.setdefault("timezone_id", "Asia/Shanghai")
            # Deterministic viewport, device scale and motion for every context so
            # geometry is measured on the final frame instead of mid-animation.
            # See tests/browser_env.py for the rationale and the opt-out.
            freeze_motion = browser_env.apply_stable_defaults(kwargs)
            context = chromium.new_context(**kwargs)
            context.add_init_script("""(() => {
                const RealDate = Date;
                const now = %d;
                window.Date = class extends RealDate {
                    constructor(...args) { super(...(args.length ? args : [now])); }
                    static now() { return now; }
                };
            })();""" % int(test_now.timestamp() * 1000))
            context.route(
                re.compile(r"^https?://fonts\.(?:googleapis|gstatic)\.com/.*"),
                lambda route: route.fulfill(status=200, content_type="text/css", body=""),
            )
            if freeze_motion:
                context.add_init_script(browser_env.STABLE_MOTION_SCRIPT)

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
        captured = _capture_failure_evidence(contexts, folder)
        if captured:
            (folder / "capture-0.txt").write_text("\n".join(captured), encoding="utf-8")
    for context in contexts:
        try:
            context.close()
        except Exception:
            pass
