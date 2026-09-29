import importlib


def test_apple_calendar_is_enabled_by_default(monkeypatch):
    monkeypatch.delenv("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", raising=False)

    import settings

    importlib.reload(settings)

    assert settings.APPLE_CALENDAR_ENABLED is True


def test_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("CANVAS_DASHBOARD_PORT", "5050")
    monkeypatch.setenv("CANVAS_DASHBOARD_THREADS", "12")
    monkeypatch.setenv("TONGJIOJ_READ_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("CANVAS_DASHBOARD_COOKIE_SECURE", "yes")
    monkeypatch.setenv("CANVAS_DASHBOARD_ICP_NUMBER", "沪ICP备00000000号-1")
    monkeypatch.setenv("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", "yes")
    monkeypatch.setenv("ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("HAOKE_BASE_URL", "https://example.invalid")

    import settings

    importlib.reload(settings)

    assert settings.APP_PORT == 5050
    assert settings.APP_THREADS == 12
    assert settings.TONGJIOJ_READ_TIMEOUT_SECONDS == 30
    assert settings.COOKIE_SECURE is True
    assert settings.ICP_NUMBER == "沪ICP备00000000号-1"
    assert settings.APPLE_CALENDAR_ENABLED is True
    assert settings.ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS == 3.5
    assert settings.HAOKE_BASE_URL == "https://example.invalid"


def test_settings_invalid_numeric_overrides_fall_back(monkeypatch):
    monkeypatch.setenv("CANVAS_DASHBOARD_PORT", "not-a-port")
    monkeypatch.setenv("CANVAS_DASHBOARD_THREADS", "not-an-int")
    monkeypatch.setenv("TONGJIOJ_READ_TIMEOUT_SECONDS", "not-an-int")
    monkeypatch.setenv("HAOKE_TENANT_ID", "not-an-int")
    monkeypatch.setenv("TONGJI_TERM_START", "not-a-date")

    import settings

    importlib.reload(settings)

    assert settings.APP_PORT == 5000
    assert settings.APP_THREADS == 8
    assert settings.TONGJIOJ_READ_TIMEOUT_SECONDS == 45
    assert settings.HAOKE_TENANT_ID == 88
    assert settings.TERM_START_DATE.isoformat() == "2026-09-14"


def test_production_config_validation(monkeypatch):
    import pytest
    import settings

    # In development mode, validation passes without requirements
    monkeypatch.setenv("CANVAS_DASHBOARD_PRODUCTION", "0")
    monkeypatch.setenv("CANVAS_DASHBOARD_ENV", "development")
    monkeypatch.setenv("CANVAS_DASHBOARD_COOKIE_SECURE", "0")
    monkeypatch.delenv("CANVAS_DASHBOARD_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("CANVAS_DASHBOARD_TRUSTED_HOSTS", raising=False)
    importlib.reload(settings)
    settings.validate_production_configuration()  # Should not raise

    # In production mode without cookie secure, raises
    monkeypatch.setenv("CANVAS_DASHBOARD_PRODUCTION", "1")
    monkeypatch.setenv("CANVAS_DASHBOARD_COOKIE_SECURE", "0")
    monkeypatch.setenv("CANVAS_DASHBOARD_PUBLIC_BASE_URL", "https://dashboard.tongji.edu.cn")
    importlib.reload(settings)
    with pytest.raises(RuntimeError, match="CANVAS_DASHBOARD_COOKIE_SECURE"):
        settings.validate_production_configuration()

    # In production mode without public url or trusted hosts, raises
    monkeypatch.setenv("CANVAS_DASHBOARD_COOKIE_SECURE", "1")
    monkeypatch.delenv("CANVAS_DASHBOARD_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("CANVAS_DASHBOARD_TRUSTED_HOSTS", raising=False)
    importlib.reload(settings)
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        settings.validate_production_configuration()

    # In production mode with http (non-https) public url, raises
    monkeypatch.setenv("CANVAS_DASHBOARD_PUBLIC_BASE_URL", "http://dashboard.tongji.edu.cn")
    importlib.reload(settings)
    with pytest.raises(RuntimeError, match="https://"):
        settings.validate_production_configuration()

    # In production mode with valid https and cookie secure, passes
    monkeypatch.setenv("CANVAS_DASHBOARD_PUBLIC_BASE_URL", "https://dashboard.tongji.edu.cn")
    importlib.reload(settings)
    settings.validate_production_configuration()

    # Reset environment back to development
    monkeypatch.setenv("CANVAS_DASHBOARD_PRODUCTION", "0")
    monkeypatch.delenv("CANVAS_DASHBOARD_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("CANVAS_DASHBOARD_TRUSTED_HOSTS", raising=False)
    importlib.reload(settings)
