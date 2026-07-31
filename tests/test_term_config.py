import datetime as dt
import json

import app as dashboard_app


def test_calendar_inference_july_18_is_week_20():
    """Verify that 2026-07-18 is calculated as 2025-2026学年 第二学期 Week 20."""
    target_dt = dt.datetime(2026, 7, 18, 12, 0, tzinfo=dashboard_app.CST)
    term_label, week_num, semester_start = dashboard_app.get_term_info(target_dt)

    assert term_label == "2025-2026学年 第二学期"
    assert week_num == 20
    assert semester_start == "2026-03-02"


def test_load_term_config_multi_semester(tmp_path, monkeypatch):
    config_file = tmp_path / "term_config.json"
    config_file.write_text(
        json.dumps({
            "semesters": [
                {
                    "term_label": "2025-2026学年 第二学期",
                    "start_date": "2026-03-02",
                    "weeks": 22,
                },
                {
                    "term_label": "2026-2027学年 第一学期",
                    "start_date": "2026-09-14",
                    "weeks": 19,
                },
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "_TERM_CONFIG_FILE", config_file)

    # First day of 2025-2026 2nd semester
    label1, week1, _ = dashboard_app._load_term_config(dt.date(2026, 3, 2))
    assert label1 == "2025-2026学年 第二学期"
    assert week1 == 1

    # July 18, 2026 (Week 20)
    label20, week20, _ = dashboard_app._load_term_config(dt.date(2026, 7, 18))
    assert label20 == "2025-2026学年 第二学期"
    assert week20 == 20

    # First day of 2026-2027 1st semester
    label_next, week_next, _ = dashboard_app._load_term_config(dt.date(2026, 9, 14))
    assert label_next == "2026-2027学年 第一学期"
    assert week_next == 1


def test_load_term_config_single_override_fallback(tmp_path, monkeypatch):
    config_file = tmp_path / "term_config.json"
    config_file.write_text(
        json.dumps({
            "term_label": "2026-2027 test term",
            "term_start": "2026-09-07",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "_TERM_CONFIG_FILE", config_file)

    label, week_num, start_str = dashboard_app._load_term_config(dt.date(2026, 9, 7))

    assert label == "2026-2027 test term"
    assert week_num == 1
    assert start_str == "2026-09-07"

