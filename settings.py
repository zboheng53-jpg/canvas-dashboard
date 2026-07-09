"""Runtime settings with environment-variable overrides."""
from datetime import date


def env_str(name: str, default: str) -> str:
    import os

    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_int(name: str, default: int) -> int:
    try:
        return int(env_str(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env_str(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = env_str(name, "1" if default else "0").strip().lower()
    return value in ("1", "true", "yes", "on")


def env_date(name: str, default: str) -> date:
    try:
        return date.fromisoformat(env_str(name, default))
    except ValueError:
        return date.fromisoformat(default)


APP_HOST = env_str("CANVAS_DASHBOARD_HOST", "127.0.0.1")
APP_PORT = env_int("CANVAS_DASHBOARD_PORT", 5000)
COOKIE_SECURE = env_bool("CANVAS_DASHBOARD_COOKIE_SECURE", False)
MAX_CONTENT_LENGTH_BYTES = env_int("CANVAS_DASHBOARD_MAX_CONTENT_LENGTH_BYTES", 8 * 1024 * 1024)

CDP_PROXY_BASE_URL = env_str("CANVAS_DASHBOARD_CDP_PROXY_BASE_URL", "http://localhost:3456").rstrip("/")
TERM_LABEL = env_str("TONGJI_TERM_LABEL", "2025-2026学年 第二学期")
TERM_START_DATE = env_date("TONGJI_TERM_START", "2026-03-02")
HOLIDAY_CACHE_TTL_SECONDS = env_int("TONGJI_HOLIDAY_CACHE_TTL_SECONDS", 24 * 60 * 60)
HOLIDAY_FETCH_RETRY_INTERVAL_SECONDS = env_int("TONGJI_HOLIDAY_FETCH_RETRY_INTERVAL_SECONDS", 60 * 60)

HAOKE_BASE_URL = env_str("HAOKE_BASE_URL", "https://tongji.aihaoke.net")
HAOKE_TENANT_ID = env_int("HAOKE_TENANT_ID", 88)
ZHIXUEMENG_BASE_URL = env_str("ZHIXUEMENG_BASE_URL", "https://admin.zhixuemeng.com/jeecg-boot")
ZHIXUEMENG_CACHE_TTL_SECONDS = env_int("ZHIXUEMENG_CACHE_TTL_SECONDS", 30 * 60)

ZHIHUISHU_CACHE_STALE_SECONDS = env_int("ZHIHUISHU_CACHE_STALE_SECONDS", 30 * 60)
ZHIHUISHU_LOGIN_SESSION_TTL_SECONDS = env_int("ZHIHUISHU_LOGIN_SESSION_TTL_SECONDS", 10 * 60)
ZHIHUISHU_LOGIN_PORT_START = env_int("ZHIHUISHU_LOGIN_PORT_START", 6100)
ZHIHUISHU_LOGIN_PORT_END = env_int("ZHIHUISHU_LOGIN_PORT_END", 6199)
ZHIHUISHU_LOGIN_DOCKER_IMAGE = env_str(
    "ZHIHUISHU_LOGIN_DOCKER_IMAGE",
    "canvas-dashboard-zhihuishu-login:latest",
)
ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS = env_float("ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS", 15.0)
ZHIHUISHU_NOVNC_READY_INTERVAL_SECONDS = env_float("ZHIHUISHU_NOVNC_READY_INTERVAL_SECONDS", 0.2)

ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS = env_int("ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS", 15 * 60)
ZHIHUISHU_FETCH_INTERVAL_SECONDS = env_int("ZHIHUISHU_FETCH_INTERVAL_SECONDS", 45 * 60)
ZHIHUISHU_MAX_FAILURE_DELAY_SECONDS = env_int("ZHIHUISHU_MAX_FAILURE_DELAY_SECONDS", 60 * 60)
ZHIHUISHU_FETCH_TIMEOUT_SECONDS = env_int("ZHIHUISHU_FETCH_TIMEOUT_SECONDS", 180)
