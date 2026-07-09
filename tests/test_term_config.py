import datetime as dt
import json

import app as dashboard_app


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
