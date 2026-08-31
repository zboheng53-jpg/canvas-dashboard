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


def test_weather_endpoint_uses_tongji_siping_campus_coordinates(tmp_path, monkeypatch):
    requested_urls = []

    class WeatherResponse:
        def json(self):
            return {"current": {"weather_code": 0}}

    def fake_get(url, **_kwargs):
        requested_urls.append(url)
        return WeatherResponse()

    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app.requests, "get", fake_get)
    dashboard_app.app.config.update(TESTING=True)

    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
        response = client.get("/api/weather")

    assert response.status_code == 200
    assert "latitude=31.28294&longitude=121.501489" in requested_urls[0]


def test_weather_endpoint_accepts_jiading_campus(tmp_path, monkeypatch):
    requested_urls = []

    class WeatherResponse:
        def json(self):
            return {"current": {"weather_code": 0}}

    def fake_get(url, **_kwargs):
        requested_urls.append(url)
        return WeatherResponse()

    monkeypatch.setattr(dashboard_app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dashboard_app.requests, "get", fake_get)
    dashboard_app.app.config.update(TESTING=True)

    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
        response = client.get("/api/weather?campus=jiading")

    assert response.status_code == 200
    assert response.get_json()["campus_name"] == "嘉定校区"
    assert "latitude=31.28984&longitude=121.17712" in requested_urls[0]


def test_weather_hail_codes_are_rendered_as_generic_severe_convection():
    assert dashboard_app.WMO_CODES[96][0] == "强对流雷雨"
    assert dashboard_app.WMO_CODES[99][0] == "强对流雷雨"


def test_greeting_info_by_hour():
    expected_mappings = {
        0: ("夜深了", "🌙", True),
        3: ("夜深了", "🌙", True),
        5: ("早上好", "🌅", False),
        8: ("早上好", "🌅", False),
        9: ("上午好", "☀️", False),
        11: ("上午好", "☀️", False),
        12: ("中午好", "☀️", False),
        13: ("中午好", "☀️", False),
        14: ("下午好", "🌤️", False),
        18: ("下午好", "🌤️", False),
        19: ("晚上好", "🌙", True),
        23: ("晚上好", "🌙", True),
    }
    for hour, (text, icon, is_night) in expected_mappings.items():
        dt = datetime(2026, 7, 18, hour, 30, 0)
        assert dashboard_app.get_greeting_info(dt) == (text, icon, is_night)
