from datetime import datetime

import app as dashboard_app


class FakeThursday(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 9, 22, 33, 7, tzinfo=tz)


def test_clock_returns_chinese_weekday_for_thursday(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app, "datetime", FakeThursday)
    dashboard_app.app.config.update(TESTING=True)

    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"

        resp = client.get("/api/clock")

    assert resp.status_code == 200
    assert resp.get_json()["weekday"] == "\u661f\u671f\u56db"


def test_weather_cloudy_response_is_chinese_and_uses_icon(tmp_path, monkeypatch):
    class WeatherResponse:
        def json(self):
            return {
                "current": {
                    "temperature_2m": 26.5,
                    "relative_humidity_2m": 89,
                    "weather_code": 3,
                    "wind_speed_10m": 14.3,
                }
            }

    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app.requests, "get", lambda *args, **kwargs: WeatherResponse())
    dashboard_app.app.config.update(TESTING=True)

    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"

        resp = client.get("/api/weather")

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["weather_desc"] == "\u9634\u5929"
    assert body["weather_emoji"] == "\u2601\ufe0f"


def test_greeting_info_by_hour():
    expected_mappings = {
        0: ("夜深了", "🌙"),
        3: ("夜深了", "🌙"),
        5: ("早上好", "🌅"),
        8: ("早上好", "🌅"),
        9: ("上午好", "☀️"),
        11: ("上午好", "☀️"),
        12: ("中午好", "☀️"),
        13: ("中午好", "☀️"),
        14: ("下午好", "🌤️"),
        18: ("下午好", "🌤️"),
        19: ("晚上好", "🌙"),
        23: ("晚上好", "🌙"),
    }
    for hour, (text, icon) in expected_mappings.items():
        dt = datetime(2026, 7, 18, hour, 30, 0)
        assert dashboard_app.get_greeting_info(dt) == (text, icon)
