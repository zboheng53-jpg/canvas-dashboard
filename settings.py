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


def _env_int_any(names: tuple[str, ...], default: int) -> int:
    for name in names:
        raw = env_str(name, "")
        if raw:
            try:
                return int(raw)
            except ValueError:
                return default
    return default


def _env_positive_str_any(names: tuple[str, ...], default: str, parser=None) -> str:
    for name in names:
        raw = env_str(name, "").strip()
        if raw:
            if parser is not None:
                try:
                    if parser(raw) <= 0:
                        return default
                except ValueError:
                    return default
            return raw
    return default


APP_HOST = env_str("CANVAS_DASHBOARD_HOST", "127.0.0.1")
APP_PORT = env_int("CANVAS_DASHBOARD_PORT", 5000)
APP_THREADS = max(1, env_int("CANVAS_DASHBOARD_THREADS", 16))
COOKIE_SECURE = env_bool("CANVAS_DASHBOARD_COOKIE_SECURE", False)
PUBLIC_BASE_URL = env_str("CANVAS_DASHBOARD_PUBLIC_BASE_URL", "").rstrip("/")
TRUSTED_HOSTS = frozenset(
    host.strip().lower()
    for host in env_str("CANVAS_DASHBOARD_TRUSTED_HOSTS", "").split(",")
    if host.strip()
)
ENV_MODE = env_str("CANVAS_DASHBOARD_ENV", "development").strip().lower()
IS_PRODUCTION = env_bool("CANVAS_DASHBOARD_PRODUCTION", False) or ENV_MODE in ("production", "prod")
RATE_LIMIT_MAX_KEYS = max(100, env_int("CANVAS_DASHBOARD_RATE_LIMIT_MAX_KEYS", 10000))
RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = max(10, env_int("CANVAS_DASHBOARD_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS", 60))
AGENT_RATE_LIMIT_ATTEMPTS = max(1, env_int("CANVAS_DASHBOARD_AGENT_RATE_LIMIT_ATTEMPTS", 240))
AGENT_RATE_LIMIT_SECONDS = max(1, env_int("CANVAS_DASHBOARD_AGENT_RATE_LIMIT_SECONDS", 60))
REGISTER_RATE_LIMIT_ATTEMPTS = max(1, env_int("CANVAS_DASHBOARD_REGISTER_RATE_LIMIT_ATTEMPTS", 5))
ICP_NUMBER = env_str("CANVAS_DASHBOARD_ICP_NUMBER", "")
APPLE_CALENDAR_ENABLED = env_bool("CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED", True)
MAX_CONTENT_LENGTH_BYTES = env_int("CANVAS_DASHBOARD_MAX_CONTENT_LENGTH_BYTES", 8 * 1024 * 1024)
LOGIN_MAX_SESSIONS = max(1, env_int("CANVAS_DASHBOARD_LOGIN_MAX_SESSIONS", 3))
LOGIN_CONTAINER_MEMORY = _env_positive_str_any(
    ("CANVAS_DASHBOARD_LOGIN_CONTAINER_MEMORY", "LOGIN_CONTAINER_MEMORY"),
    "768m",
)
LOGIN_CONTAINER_CPUS = _env_positive_str_any(
    ("CANVAS_DASHBOARD_LOGIN_CONTAINER_CPUS", "LOGIN_CONTAINER_CPUS"),
    "0.75",
    parser=float,
)
LOGIN_CONTAINER_PIDS_LIMIT = _env_positive_str_any(
    ("CANVAS_DASHBOARD_LOGIN_CONTAINER_PIDS_LIMIT", "LOGIN_CONTAINER_PIDS_LIMIT"),
    "384",
    parser=int,
)
HTTP_SYNC_MAX_WORKERS = max(1, env_int("HTTP_SYNC_MAX_WORKERS", 6))
HTTP_SYNC_MAX_JOBS = max(HTTP_SYNC_MAX_WORKERS, env_int("HTTP_SYNC_MAX_JOBS", 96))
REMOTE_OPERATIONS_MAX_TASKS = max(
    1,
    _env_int_any(("CANVAS_DASHBOARD_REMOTE_OPERATIONS_MAX_TASKS", "REMOTE_OPERATIONS_MAX_TASKS"), 192),
)
MONITOR_LOW_MEM_MIB = max(0, env_int("CANVAS_DASHBOARD_MONITOR_LOW_MEM_MIB", 768))
REGISTRATION_ENABLED = env_bool("CANVAS_DASHBOARD_REGISTRATION_ENABLED", True)
# Pre-launch capacity guard: close new registrations as soon as one admission
# threshold is reached, so parallel load cannot take the single Web process
# down. A threshold of 0 (or a negative value) disables only that threshold.
CAPACITY_GUARD_ENABLED = env_bool("CANVAS_DASHBOARD_CAPACITY_GUARD_ENABLED", True)
CAPACITY_MAX_TOTAL_USERS = env_int("CANVAS_DASHBOARD_CAPACITY_MAX_TOTAL_USERS", 60)
CAPACITY_MAX_ACTIVE_USERS = env_int("CANVAS_DASHBOARD_CAPACITY_MAX_ACTIVE_USERS", 40)
CAPACITY_MAX_CONNECTED_PLATFORMS = env_int("CANVAS_DASHBOARD_CAPACITY_MAX_CONNECTED_PLATFORMS", 180)
CAPACITY_ACTIVE_WINDOW_DAYS = max(1, env_int("CANVAS_DASHBOARD_CAPACITY_ACTIVE_WINDOW_DAYS", 14))
CANVAS_FEED_HOSTS = frozenset(host.strip().lower() for host in env_str(
    "CANVAS_DASHBOARD_CANVAS_FEED_HOSTS", "canvas.tongji.edu.cn"
).split(",") if host.strip())


def validate_production_configuration() -> None:
    """Assert required security configurations when running in production mode."""
    if not IS_PRODUCTION:
        return
    if not COOKIE_SECURE:
        raise RuntimeError("生产模式下必须启用安全 Cookie: CANVAS_DASHBOARD_COOKIE_SECURE=1")
    if not PUBLIC_BASE_URL and not TRUSTED_HOSTS:
        raise RuntimeError("生产模式下必须配置 CANVAS_DASHBOARD_PUBLIC_BASE_URL 或 CANVAS_DASHBOARD_TRUSTED_HOSTS")
    if PUBLIC_BASE_URL and not PUBLIC_BASE_URL.startswith("https://"):
        raise RuntimeError(f"生产模式下的 PUBLIC_BASE_URL 必须为 https://: {PUBLIC_BASE_URL}")


CDP_PROXY_BASE_URL = env_str("CANVAS_DASHBOARD_CDP_PROXY_BASE_URL", "http://localhost:3456").rstrip("/")
TERM_LABEL = env_str("TONGJI_TERM_LABEL", "2026-2027学年 第一学期")
TERM_START_DATE = env_date("TONGJI_TERM_START", "2026-09-14")

HAOKE_BASE_URL = env_str("HAOKE_BASE_URL", "https://tongji.aihaoke.net")
HAOKE_TENANT_ID = env_int("HAOKE_TENANT_ID", 88)
ZHIXUEMENG_BASE_URL = env_str("ZHIXUEMENG_BASE_URL", "https://admin.zhixuemeng.com/jeecg-boot")
ZHIXUEMENG_CACHE_TTL_SECONDS = env_int("ZHIXUEMENG_CACHE_TTL_SECONDS", 30 * 60)
KETANGPAI_BASE_URL = env_str("KETANGPAI_BASE_URL", "https://openapiv5.ketangpai.com")
KETANGPAI_WEB_URL = env_str("KETANGPAI_WEB_URL", "https://w.ketangpai.com")
TONGJIOJ_CACHE_TTL_SECONDS = env_int("TONGJIOJ_CACHE_TTL_SECONDS", 30 * 60)
TONGJIOJ_READ_TIMEOUT_SECONDS = max(1, env_int("TONGJIOJ_READ_TIMEOUT_SECONDS", 45))
TONGJIOJ_VPN_PROXY_URL = env_str("TONGJIOJ_VPN_PROXY_URL", "")

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

TONGJI_LOGIN_SESSION_TTL_SECONDS = env_int("TONGJI_LOGIN_SESSION_TTL_SECONDS", 10 * 60)
TONGJI_LOGIN_PORT_START = env_int("TONGJI_LOGIN_PORT_START", 6200)
TONGJI_LOGIN_PORT_END = env_int("TONGJI_LOGIN_PORT_END", 6299)
TONGJI_LOGIN_DEBUG_PORT_START = env_int("TONGJI_LOGIN_DEBUG_PORT_START", 6300)
TONGJI_LOGIN_DEBUG_PORT_END = env_int("TONGJI_LOGIN_DEBUG_PORT_END", 6399)
TONGJI_LOGIN_DOCKER_IMAGE = env_str("TONGJI_LOGIN_DOCKER_IMAGE", ZHIHUISHU_LOGIN_DOCKER_IMAGE)
TONGJI_NOVNC_READY_TIMEOUT_SECONDS = env_float("TONGJI_NOVNC_READY_TIMEOUT_SECONDS", 15.0)
TONGJI_NOVNC_READY_INTERVAL_SECONDS = env_float("TONGJI_NOVNC_READY_INTERVAL_SECONDS", 0.2)

ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS = env_int("ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS", 15 * 60)
ZHIHUISHU_FETCH_INTERVAL_SECONDS = env_int("ZHIHUISHU_FETCH_INTERVAL_SECONDS", 45 * 60)
ZHIHUISHU_MAX_FAILURE_DELAY_SECONDS = env_int("ZHIHUISHU_MAX_FAILURE_DELAY_SECONDS", 60 * 60)
ZHIHUISHU_FETCH_TIMEOUT_SECONDS = env_int("ZHIHUISHU_FETCH_TIMEOUT_SECONDS", 180)
ZHIHUISHU_WORKER_MAX_CONCURRENCY = max(
    1,
    _env_int_any(("ZHIHUISHU_WORKER_MAX_CONCURRENCY", "CANVAS_DASHBOARD_ZHIHUISHU_WORKER_MAX_CONCURRENCY"), 2),
)
