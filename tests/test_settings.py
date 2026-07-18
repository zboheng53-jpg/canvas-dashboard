import importlib


def test_apple_calendar_is_enabled_by_default(monkeypatch):
    monkeypatch.delenv("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", raising=False)

    import settings

    importlib.reload(settings)

    assert settings.APPLE_CALENDAR_ENABLED is True


def test_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("CANVAS_DASHBOARD_PORT", "5050")
    monkeypatch.setenv("CANVAS_DASHBOARD_COOKIE_SECURE", "yes")
    monkeypatch.setenv("CANVAS_DASHBOARD_ICP_NUMBER", "沪ICP备00000000号-1")
    monkeypatch.setenv("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", "yes")
    monkeypatch.setenv("ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("HAOKE_BASE_URL", "https://example.invalid")

    import settings

    importlib.reload(settings)

    assert settings.APP_PORT == 5050
    assert settings.COOKIE_SECURE is True
    assert settings.ICP_NUMBER == "沪ICP备00000000号-1"
    assert settings.APPLE_CALENDAR_ENABLED is True
    assert settings.ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS == 3.5
    assert settings.HAOKE_BASE_URL == "https://example.invalid"


def test_settings_invalid_numeric_overrides_fall_back(monkeypatch):
    monkeypatch.setenv("CANVAS_DASHBOARD_PORT", "not-a-port")
    monkeypatch.setenv("HAOKE_TENANT_ID", "not-an-int")
    monkeypatch.setenv("TONGJI_TERM_START", "not-a-date")

    import settings

    importlib.reload(settings)

    assert settings.APP_PORT == 5000
    assert settings.HAOKE_TENANT_ID == 88
    assert settings.TERM_START_DATE.isoformat() == "2026-03-02"
