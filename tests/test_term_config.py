import datetime as dt
import json

import app as dashboard_app


def test_term_refresh_failure_returns_readable_utf8_chinese(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_scrape_term_from_tongji", lambda: None)
    dashboard_app.app.config.update(TESTING=True)

    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "term-refresh-token"
        response = client.post(
            "/api/term/refresh",
            headers={"X-CSRF-Token": "term-refresh-token"},
        )

    assert response.status_code == 502
    assert response.get_json() == {
        "ok": False,
        "error": "CDP 抓取失败，请确认已登录 1.tongji.edu.cn 且 CDP proxy 正在运行",
    }
    assert "�" not in response.get_data(as_text=True)


def test_load_term_config_reads_json_override(tmp_path, monkeypatch):
    config_file = tmp_path / "term_config.json"
    config_file.write_text(
        json.dumps(
            {
                "term_label": "2026-2027 test term",
                "term_start": "2026-09-07",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "_TERM_CONFIG_FILE", config_file)

    label, start_date = dashboard_app._load_term_config()

    assert label == "2026-2027 test term"
    assert start_date == dt.date(2026, 9, 7)
