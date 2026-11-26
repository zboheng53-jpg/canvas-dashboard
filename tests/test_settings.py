import importlib


def test_apple_calendar_is_enabled_by_default(monkeypatch):
    monkeypatch.delenv("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", raising=False)

    import settings

    importlib.reload(settings)

    assert settings.APPLE_CALENDAR_ENABLED is True


def test_2c8g_capacity_defaults(monkeypatch):
    import settings

    with monkeypatch.context() as mp:
        for name in (
            "CANVAS_DASHBOARD_THREADS",
            "HTTP_SYNC_MAX_WORKERS",
            "HTTP_SYNC_MAX_JOBS",
            "REMOTE_OPERATIONS_MAX_TASKS",
            "CANVAS_DASHBOARD_REMOTE_OPERATIONS_MAX_TASKS",
            "CANVAS_DASHBOARD_LOGIN_MAX_SESSIONS",
            "LOGIN_CONTAINER_MEMORY",
            "CANVAS_DASHBOARD_LOGIN_CONTAINER_MEMORY",
            "LOGIN_CONTAINER_CPUS",
            "CANVAS_DASHBOARD_LOGIN_CONTAINER_CPUS",
            "LOGIN_CONTAINER_PIDS_LIMIT",
            "CANVAS_DASHBOARD_LOGIN_CONTAINER_PIDS_LIMIT",
            "ZHIHUISHU_WORKER_MAX_CONCURRENCY",
            "CANVAS_DASHBOARD_ZHIHUISHU_WORKER_MAX_CONCURRENCY",
            "CANVAS_DASHBOARD_CAPACITY_MAX_TOTAL_USERS",
            "CANVAS_DASHBOARD_CAPACITY_MAX_ACTIVE_USERS",
            "CANVAS_DASHBOARD_CAPACITY_MAX_CONNECTED_PLATFORMS",
            "CANVAS_DASHBOARD_AGENT_RATE_LIMIT_ATTEMPTS",
            "CANVAS_DASHBOARD_REGISTER_RATE_LIMIT_ATTEMPTS",
            "CANVAS_DASHBOARD_MONITOR_LOW_MEM_MIB",
        ):
            mp.delenv(name, raising=False)
        importlib.reload(settings)

        assert settings.APP_THREADS == 16
        assert settings.HTTP_SYNC_MAX_WORKERS == 6
        assert settings.HTTP_SYNC_MAX_JOBS == 96
        assert settings.REMOTE_OPERATIONS_MAX_TASKS == 192
        assert settings.LOGIN_MAX_SESSIONS == 3
        assert settings.LOGIN_CONTAINER_MEMORY == "768m"
        assert settings.LOGIN_CONTAINER_CPUS == "0.75"
        assert settings.LOGIN_CONTAINER_PIDS_LIMIT == "384"
        assert settings.ZHIHUISHU_WORKER_MAX_CONCURRENCY == 2
        assert settings.CAPACITY_MAX_TOTAL_USERS == 60
        assert settings.CAPACITY_MAX_ACTIVE_USERS == 40
        assert settings.CAPACITY_MAX_CONNECTED_PLATFORMS == 180
        assert settings.AGENT_RATE_LIMIT_ATTEMPTS == 240
        assert settings.REGISTER_RATE_LIMIT_ATTEMPTS == 5
        assert settings.MONITOR_LOW_MEM_MIB == 768
    importlib.reload(settings)


def test_settings_env_overrides(monkeypatch):
    import settings

    with monkeypatch.context() as mp:
        mp.setenv("CANVAS_DASHBOARD_PORT", "5050")
        mp.setenv("CANVAS_DASHBOARD_THREADS", "12")
        mp.setenv("TONGJIOJ_READ_TIMEOUT_SECONDS", "30")
        mp.setenv("CANVAS_DASHBOARD_COOKIE_SECURE", "yes")
        mp.setenv("CANVAS_DASHBOARD_ICP_NUMBER", "沪ICP备00000000号-1")
        mp.setenv("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", "yes")
        mp.setenv("ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS", "3.5")
        mp.setenv("HAOKE_BASE_URL", "https://example.invalid")
        mp.setenv("REMOTE_OPERATIONS_MAX_TASKS", "256")
        mp.setenv("LOGIN_CONTAINER_MEMORY", "1g")
        mp.setenv("LOGIN_CONTAINER_CPUS", "1.0")
        mp.setenv("LOGIN_CONTAINER_PIDS_LIMIT", "512")
        mp.setenv("ZHIHUISHU_WORKER_MAX_CONCURRENCY", "3")
        mp.setenv("CANVAS_DASHBOARD_REGISTER_RATE_LIMIT_ATTEMPTS", "9")
        mp.setenv("CANVAS_DASHBOARD_MONITOR_LOW_MEM_MIB", "1024")

        importlib.reload(settings)

        assert settings.APP_PORT == 5050
        assert settings.APP_THREADS == 12
        assert settings.TONGJIOJ_READ_TIMEOUT_SECONDS == 30
        assert settings.COOKIE_SECURE is True
        assert settings.ICP_NUMBER == "沪ICP备00000000号-1"
        assert settings.APPLE_CALENDAR_ENABLED is True
        assert settings.ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS == 3.5
        assert settings.HAOKE_BASE_URL == "https://example.invalid"
        assert settings.REMOTE_OPERATIONS_MAX_TASKS == 256
        assert settings.LOGIN_CONTAINER_MEMORY == "1g"
        assert settings.LOGIN_CONTAINER_CPUS == "1.0"
        assert settings.LOGIN_CONTAINER_PIDS_LIMIT == "512"
        assert settings.ZHIHUISHU_WORKER_MAX_CONCURRENCY == 3
        assert settings.REGISTER_RATE_LIMIT_ATTEMPTS == 9
        assert settings.MONITOR_LOW_MEM_MIB == 1024
    importlib.reload(settings)


def test_settings_invalid_numeric_overrides_fall_back(monkeypatch):
    import settings

    with monkeypatch.context() as mp:
        mp.setenv("CANVAS_DASHBOARD_PORT", "not-a-port")
        mp.setenv("CANVAS_DASHBOARD_THREADS", "not-an-int")
        mp.setenv("TONGJIOJ_READ_TIMEOUT_SECONDS", "not-an-int")
        mp.setenv("HAOKE_TENANT_ID", "not-an-int")
        mp.setenv("TONGJI_TERM_START", "not-a-date")
        mp.setenv("REMOTE_OPERATIONS_MAX_TASKS", "not-an-int")
        mp.setenv("LOGIN_CONTAINER_CPUS", "-1")
        mp.setenv("LOGIN_CONTAINER_PIDS_LIMIT", "bad")
        mp.setenv("ZHIHUISHU_WORKER_MAX_CONCURRENCY", "bad")
        mp.setenv("CANVAS_DASHBOARD_REGISTER_RATE_LIMIT_ATTEMPTS", "bad")
        mp.setenv("CANVAS_DASHBOARD_MONITOR_LOW_MEM_MIB", "bad")

        importlib.reload(settings)

        assert settings.APP_PORT == 5000
        assert settings.APP_THREADS == 16
        assert settings.TONGJIOJ_READ_TIMEOUT_SECONDS == 45
        assert settings.HAOKE_TENANT_ID == 88
        assert settings.TERM_START_DATE.isoformat() == "2026-09-14"
        assert settings.REMOTE_OPERATIONS_MAX_TASKS == 192
        assert settings.LOGIN_CONTAINER_CPUS == "0.75"
        assert settings.LOGIN_CONTAINER_PIDS_LIMIT == "384"
        assert settings.ZHIHUISHU_WORKER_MAX_CONCURRENCY == 2
        assert settings.REGISTER_RATE_LIMIT_ATTEMPTS == 5
        assert settings.MONITOR_LOW_MEM_MIB == 768
    importlib.reload(settings)


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
