import threading
from datetime import datetime
import pytest
from werkzeug.serving import make_server

import app as dashboard_app
import user_paths

playwright_api = pytest.importorskip("playwright.sync_api")
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

    server = make_server("127.0.0.1", 0, dashboard_app.app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    host, port = server.server_address
    url = f"http://{host}:{port}"
    yield url
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()
