"""Canvas Dashboard - Flask backend for Tongji University students."""
import agent_auth
import apple_calendar
import auth
import dashboard_preferences
import hmac
import io
import json
import ketangpai_client
import logging
import os
import platform_sync
import platform_http
import http_sync
import runtime_metrics
from remote_operations import background_operation, task_status
import requests
import secrets
import settings
import shutil
import threading
import time
import tongji_login_sessions
import tongji_oj_client
import zhihuishu_login_sessions
import zhihuishu_store
import zhihuishu_worker
import zipfile
from static_assets import load_manifest
from action_contract import ActionConflictError, ActionValidationError
from agent_mcp import WRITING_RULES
from canvas_auth import (
    delete_expired_completed as delete_canvas_expired_completed,
    cached_items as canvas_cached_items,
    delete_expired_hidden as delete_canvas_expired_hidden,
    fetch_canvas_planner,
    get_cached_todos as get_canvas_cached_todos,
    has_feed_url,
    is_refreshing as is_canvas_refreshing,
    load_state,
    remove_feed_url,
    save_feed_url,
    save_state,
    start_background_refresh as start_canvas_background_refresh,
    update_override as update_canvas_override,
    update_state,
)
from datetime import datetime, timedelta
from external_subtasks import attach_subtasks, save_subtasks
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session
from haoke_client import (
    delete_expired_completed as delete_haoke_expired_completed,
    clear_credentials as clear_haoke_credentials,
    delete_expired_hidden as delete_haoke_expired_hidden,
    fetch_haoke_todos,
    get_cached_todos as get_haoke_cached_todos,
    has_credentials as has_haoke_credentials,
    is_refreshing as is_haoke_refreshing,
    load_state as load_haoke_state,
    save_credentials as save_haoke_credentials,
    save_state as save_haoke_state,
    start_background_refresh as start_haoke_background_refresh,
    update_override as update_haoke_override,
    update_state as update_haoke_state,
)
from ketangpai_client import (
    delete_expired_completed as delete_ktp_expired_completed,
    delete_expired_hidden as delete_ktp_expired_hidden,
    fetch_assignments as fetch_ktp_assignments,
    fetch_courses as fetch_ktp_courses,
    has_token as has_ktp_token,
    load_state as load_ktp_state,
    logout as ktp_logout,
    password_login as ktp_password_login,
    phone_login as ktp_phone_login,
    save_state as save_ktp_state,
    send_sms as ktp_send_sms,
    update_override as update_ktp_override,
    update_state as update_ktp_state,
)
from login_capacity import LoginCapacityError
from pathlib import Path
from platform_state import build_platform_todos_response
from routes.agent import bp as agent_bp
from routes.planning import bp as planning_bp
from services.academic import _check_today_holiday, get_term_info
from services.workspace import CALENDAR_CATEGORIES, CATEGORY_ALIASES, _calendar_items, _parse_calendar_due
from storage import JsonFileCorruptionError, read_json_file
from tongji_oj_client import (
    delete_expired_completed as delete_tjoj_expired_completed,
    delete_expired_hidden as delete_tjoj_expired_hidden,
    get_selected_course as get_tjoj_selected_course,
    has_credentials as has_tjoj_credentials,
    iam_login as tjoj_iam_login,
    iam_send_second_auth_code as tjoj_iam_send_second_auth_code,
    iam_verify_second_auth_code as tjoj_iam_verify_second_auth_code,
    load_state as load_tjoj_state,
    local_login as tjoj_local_login,
    logout as tjoj_logout,
    save_state as save_tjoj_state,
    set_selected_course as set_tjoj_selected_course,
    update_override as update_tjoj_override,
    update_state as update_tjoj_state,
)
from user_paths import DATA_DIR, user_dir
from web_common import (
    CST,
    _get_external_base_url,
    _with_default_error_code,
    api_error,
    invalid_request_response,
    read_json_request,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from zhixuemeng_client import (
    delete_expired_completed as delete_zxm_expired_completed,
    delete_expired_hidden as delete_zxm_expired_hidden,
    fetch_assignments as fetch_zxm_assignments,
    fetch_courses as fetch_zxm_courses,
    get_selected_course,
    has_token as has_zxm_token,
    load_state as load_zxm_state,
    logout as zxm_logout,
    password_login,
    phone_login,
    save_selected_course,
    save_state as save_zxm_state,
    send_sms,
    update_override as update_zxm_override,
    update_state as update_zxm_state,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("app")

app = Flask(
    __name__,
    static_folder="frontend/assets",
    static_url_path="/static",
    template_folder="frontend/templates",
)
app.json.ensure_ascii = False
app.secret_key = auth.get_secret_key()
app.permanent_session_lifetime = auth.SESSION_LIFETIME
app.config["MAX_CONTENT_LENGTH"] = settings.MAX_CONTENT_LENGTH_BYTES
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=settings.COOKIE_SECURE,
    SESSION_REFRESH_EACH_REQUEST=False,
)
settings.validate_production_configuration()
_asset_manifest = load_manifest(app.static_folder)


@app.url_defaults
def _fingerprint_static_urls(endpoint, values):
    if endpoint == 'static' and values.get('filename') in _asset_manifest:
        values['filename'] = _asset_manifest[values['filename']]
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_prefix=0)


@app.before_request
def _record_request_start():
    if request.path.startswith("/api/"):
        g.metrics_started = time.monotonic()
        runtime_metrics.request_started()


@app.before_request
def _validate_trusted_host_and_environment():
    from urllib.parse import urlsplit
    allowed = set(settings.TRUSTED_HOSTS)
    if settings.PUBLIC_BASE_URL:
        allowed.add(urlsplit(settings.PUBLIC_BASE_URL).hostname)
    if allowed:
        raw_host = request.headers.get("Host", "").strip() or request.host
        host_only = raw_host.split(":")[0].lower() if raw_host else ""
        if host_only not in allowed and host_only not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return jsonify({"ok": False, "error": "Invalid Host Header"}), 400


@app.after_request
def _apply_security_and_cache_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    endpoint = request.endpoint
    if endpoint == "static":
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if request.view_args.get('filename', '').startswith('built/')
            else "public, max-age=0, must-revalidate"
        )
    elif response.mimetype == 'text/html' or request.path.startswith("/api/") or endpoint in (
        "index",
        "component_lab",
        "site_login_page",
        "site_register_page",
        "site_privacy_page",
        "site_welcome_page",
    ):
        response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(ActionValidationError)
def action_validation_error(error):
    return jsonify({"ok": False, "code": "invalid_action", "error": str(error)}), 400


@app.errorhandler(ActionConflictError)
def action_conflict_error(error):
    return jsonify({"ok": False, "code": "action_conflict", "error": str(error)}), 409


# Routes reachable without being logged in.
_LOGIN_EXEMPT_ENDPOINTS = {
    "site_login_page",
    "site_register_page",
    "site_privacy_page",
    "site_welcome_page",
    "api_auth_register",
    "api_auth_login",
    "calendar_subscription",
    "calendar_category_subscription",
    "healthz",
    "livez",
    "readyz",
    "site_password_reset_page",
    "api_auth_password_reset",
    "static",
    "api_skill_readme",
    "api_skill_file",
}

_CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CSRF_HEADER = "X-CSRF-Token"
_CSRF_SESSION_KEY = "_csrf_token"
_SESSION_ACTIVITY_KEY = "last_active_at"
SESSION_ACTIVITY_MIN_INTERVAL = timedelta(hours=12)

LOGIN_RATE_LIMIT_ATTEMPTS = 8
LOGIN_RATE_LIMIT_SECONDS = 5 * 60
REGISTER_RATE_LIMIT_ATTEMPTS = 5
REGISTER_RATE_LIMIT_SECONDS = 30 * 60
SMS_RATE_LIMIT_ATTEMPTS = 3
SMS_RATE_LIMIT_SECONDS = 10 * 60
_rate_limit_buckets = {}
_rate_limit_lock = threading.Lock()
_last_rate_limit_cleanup = 0.0


def _clean_rate_limit_buckets_locked(now: float):
    global _last_rate_limit_cleanup
    if (
        now - _last_rate_limit_cleanup < settings.RATE_LIMIT_CLEANUP_INTERVAL_SECONDS
        and len(_rate_limit_buckets) < settings.RATE_LIMIT_MAX_KEYS
    ):
        return
    _last_rate_limit_cleanup = now
    cutoff_hour = now - 3600
    expired = [k for k, ts in _rate_limit_buckets.items() if not ts or max(ts) < cutoff_hour]
    for k in expired:
        _rate_limit_buckets.pop(k, None)
    if len(_rate_limit_buckets) > settings.RATE_LIMIT_MAX_KEYS:
        excess = len(_rate_limit_buckets) - settings.RATE_LIMIT_MAX_KEYS
        sorted_keys = sorted(
            _rate_limit_buckets.keys(),
            key=lambda k: max(_rate_limit_buckets[k]) if _rate_limit_buckets[k] else 0,
        )
        for k in sorted_keys[:excess]:
            _rate_limit_buckets.pop(k, None)


def _check_data_writable():
    """Verify local storage directory and fail-closed data corruption check without disk write probes."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not DATA_DIR.is_dir():
            return {"ok": False, "error": "NotADirectory"}
        if not os.access(DATA_DIR, os.W_OK | os.X_OK):
            return {"ok": False, "error": "PermissionDenied"}
        # Fail closed on data corruption
        users_file = DATA_DIR / "users.json"
        if users_file.exists():
            read_json_file(users_file, {})
        return {"ok": True}
    except JsonFileCorruptionError as exc:
        return {"ok": False, "error": "JsonFileCorruptionError", "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


_worker_cache_lock = threading.Lock()
_worker_cache_data = {"last_time": 0.0, "result": None}


def _check_zhihuishu_worker_cached():
    if app.testing:
        return _check_zhihuishu_worker()
    now = time.time()
    with _worker_cache_lock:
        if now - _worker_cache_data["last_time"] < 30.0 and _worker_cache_data["result"] is not None:
            return dict(_worker_cache_data["result"])
    res = _check_zhihuishu_worker()
    with _worker_cache_lock:
        _worker_cache_data["last_time"] = now
        _worker_cache_data["result"] = res
    return res



def _check_zhihuishu_worker():
    users_dir = zhihuishu_store.DATA_DIR / "users"
    result = {
        "ok": True,
        "user_count": 0,
        "status_file_count": 0,
        "error_count": 0,
        "unreadable_count": 0,
        "states": {},
        "last_success_count": 0,
        "last_success_at": None,
        "oldest_last_success_at": None,
        "last_success_age_seconds": None,
        "lock_file_present": zhihuishu_worker.LOCK_FILE.exists(),
    }
    last_success_values = []
    try:
        heartbeat = read_json_file(zhihuishu_store.DATA_DIR / 'worker_heartbeat.json', {})
    except JsonFileCorruptionError:
        heartbeat = {}
        result['unreadable_count'] += 1
    heartbeat_at = heartbeat.get('at')
    heartbeat_pid = heartbeat.get('pid', 0)
    alive = False
    if isinstance(heartbeat_pid, int) and heartbeat_pid > 0:
        from login_capacity import _pid_is_running
        alive = _pid_is_running(heartbeat_pid)
    result['heartbeat_at'] = heartbeat_at
    result['heartbeat_fresh'] = bool(alive and isinstance(heartbeat_at, (int, float)) and
                                    0 <= time.time() - heartbeat_at <= settings.ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS + settings.ZHIHUISHU_FETCH_TIMEOUT_SECONDS + 60)
    try:
        if not users_dir.exists():
            return result
        for user_dir_path in users_dir.iterdir():
            if not user_dir_path.is_dir():
                continue
            result["user_count"] += 1
            status_file = user_dir_path / "zhihuishu_status.json"
            if not status_file.exists():
                continue
            result["status_file_count"] += 1
            status = read_json_file(status_file, {})
            worker_state = status.get("worker", "unknown")
            result["states"][worker_state] = result["states"].get(worker_state, 0) + 1
            if worker_state == "error":
                result["error_count"] += 1
            last_success_at = status.get("last_success_at")
            if isinstance(last_success_at, (int, float)):
                last_success_values.append(float(last_success_at))
    except Exception:
        result["unreadable_count"] += 1

    if last_success_values:
        result["last_success_count"] = len(last_success_values)
        result["last_success_at"] = max(last_success_values)
        result["oldest_last_success_at"] = min(last_success_values)
        result["last_success_age_seconds"] = max(0, round(time.time() - result["last_success_at"]))
    result["ok"] = result["error_count"] == 0 and result["unreadable_count"] == 0 and (
        not result['status_file_count'] or result['heartbeat_fresh'])
    return result


@app.route("/livez")
def livez():
    """Web liveness probe."""
    return jsonify({"ok": True, "status": "alive"}), 200


@app.route("/readyz")
def readyz():
    """Local storage readiness probe; fails closed if critical storage or data is corrupt."""
    storage = _check_data_writable()
    ok = storage.get("ok") is True
    return jsonify({"ok": ok, "status": "ready" if ok else "unready", "checks": {"storage": storage}}), 200 if ok else 503


@app.route("/healthz")
def healthz():
    """Deployment health check; degrades on third-party worker errors without returning 503."""
    storage = _check_data_writable()
    worker = _check_zhihuishu_worker_cached()
    storage_ok = storage.get("ok") is True
    checks = {
        "app": {"ok": True},
        "data_writable": storage,
        "zhihuishu_worker": worker,
    }
    ok = storage_ok
    status = "healthy" if (storage_ok and worker.get("ok")) else ("degraded" if storage_ok else "unhealthy")
    return jsonify({"ok": ok, "status": status, "checks": checks}), 200 if ok else 503


@app.route("/api/diagnostics/workers")
def api_diagnostics_workers():
    """Diagnostic endpoint reporting background worker heartbeat and platform states."""
    worker = _check_zhihuishu_worker()
    return jsonify({
        "ok": True,
        "worker": worker,
        "timestamp": time.time(),
    })


def _get_or_create_csrf_token():
    token = session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return token


@app.context_processor
def _inject_csrf_token():
    return {"csrf_token": _get_or_create_csrf_token}


def _csrf_failed_response():
    return jsonify({"ok": False, "error": "CSRF token missing or invalid"}), 403


def _refresh_session_activity(*, force: bool = False) -> bool:
    """Renew only explicit human activity, with a server-side throttle."""
    now = datetime.now(CST)
    raw = session.get(_SESSION_ACTIVITY_KEY)
    try:
        previous = datetime.fromisoformat(raw) if raw else None
        if previous and previous.tzinfo is None:
            previous = previous.replace(tzinfo=CST)
    except (TypeError, ValueError):
        previous = None
    if not force and previous and now - previous < SESSION_ACTIVITY_MIN_INTERVAL:
        return False
    session[_SESSION_ACTIVITY_KEY] = now.isoformat()
    session.permanent = True
    return True


def _request_ip():
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    return request.remote_addr or "unknown"


def _rate_limit_key(scope, identity):
    normalized_identity = (identity or "").strip().lower() or "-"
    return scope, _request_ip(), normalized_identity


def _check_rate_limit(scope, identity, attempts, window_seconds):
    now = time.time()
    cutoff = now - window_seconds
    key = _rate_limit_key(scope, identity)
    with _rate_limit_lock:
        _clean_rate_limit_buckets_locked(now)
        timestamps = [ts for ts in _rate_limit_buckets.get(key, []) if ts > cutoff]
        if len(timestamps) >= attempts:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
            _rate_limit_buckets[key] = timestamps
            return False, retry_after
        timestamps.append(now)
        _rate_limit_buckets[key] = timestamps
    return True, None



app.config['AGENT_RATE_LIMITER'] = _check_rate_limit


def _rate_limited_response(retry_after):
    resp = jsonify({"ok": False, "error": "Too many attempts; try again later."})
    resp.status_code = 429
    resp.headers["Retry-After"] = str(retry_after)
    return resp


def _haoke_default_error_code(result):
    if result.get("need_setup"):
        return "haoke_credentials_missing"
    return "haoke_fetch_failed"


def _platform_cache_path(username: str, platform: str) -> Path:
    return user_dir(username) / {
        "canvas": "canvas_cache.json",
        "haoke": "haoke_cache.json",
        "zhixuemeng": "zhixuemeng_cache.json",
        "zhihuishu": "zhihuishu_cache.json",
        "ketangpai": "ketangpai_cache.json",
        "tongjioj": "tongjioj_cache.json",
    }[platform]


def _attach_sync(result: dict, platform: str, *, connection_state: str, refreshing: bool = False) -> dict:
    result = dict(result)
    result["sync"] = platform_sync.response_sync(
        session["username"], platform, connection_state=connection_state,
        has_cache=_platform_cache_path(session["username"], platform).exists(), refreshing=refreshing,
    )
    return result


def _clear_json_file(path: Path) -> None:
    """Delete only a known file and never silently erase malformed JSON."""
    if path.exists():
        read_json_file(path, {})
        from storage import delete_file
        delete_file(path)


@app.before_request
def _require_login():
    if request.endpoint in _LOGIN_EXEMPT_ENDPOINTS or request.endpoint is None:
        return
    if request.path.startswith("/api/agent/v1/"):
        return
    username = session.get("username")
    if not username:
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return redirect("/login")
    raw_active_at = session.get(_SESSION_ACTIVITY_KEY)
    if raw_active_at:
        try:
            active_at = datetime.fromisoformat(raw_active_at)
            if active_at.tzinfo is None:
                active_at = active_at.replace(tzinfo=CST)
            if datetime.now(CST) - active_at > auth.SESSION_LIFETIME:
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "unauthorized"}), 401
                return redirect("/login")
        except (TypeError, ValueError):
            # A pre-upgrade cookie is initialized on the next explicit visit.
            pass
    # New sessions bind to a non-reusable account identity and a session
    # version.  TESTING keeps legacy fixture sessions concise; production does
    # not accept username-only cookies.
    has_identity_claims = "account_id" in session or "session_version" in session
    if (not app.testing or has_identity_claims) and not auth.validate_session_identity(
        username, session.get("account_id"), session.get("session_version")
    ):
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return redirect("/login")

    operation = auth.identity_scope(username, (session["account_id"], session["session_version"])
                                    if has_identity_claims else auth.session_identity(username))
    operation.__enter__()
    g.account_operation = operation


@app.errorhandler(auth.AccountIdentityChanged)
def handle_account_identity_changed(error):
    return api_error("account_changed", "账户或平台连接已变更，请刷新后重试", 409)


@app.errorhandler(JsonFileCorruptionError)
def handle_json_file_corruption(error):
    logger.error("Stored JSON is corrupt: %s", error)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "stored data is temporarily unavailable"}), 503
    return "Stored data is temporarily unavailable.", 503


@app.teardown_request
def _release_account_operation(error=None):
    started = g.pop("metrics_started", None)
    if started is not None:
        runtime_metrics.request_finished(request.endpoint or "unknown", request.method, 500,
                                         time.monotonic() - started)
    operation = g.pop("account_operation", None)
    if operation:
        operation.__exit__(None, None, None)


@app.before_request
def _protect_csrf():
    if request.method not in _CSRF_METHODS:
        return
    if request.path.startswith("/api/agent/v1/"):
        return
    expected = session.get(_CSRF_SESSION_KEY)
    supplied = request.headers.get(_CSRF_HEADER, "")
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        return _csrf_failed_response()


WMO_CODES = {
    0: ("\u6674\u5929", "\u2600\ufe0f"),
    1: ("\u6674\u95f4\u591a\u4e91", "\U0001f324\ufe0f"),
    2: ("\u591a\u4e91", "\u26c5"),
    3: ("\u9634\u5929", "\u2601\ufe0f"),
    45: ("\u96fe", "\U0001f32b\ufe0f"),
    48: ("\u96fe\u51c7", "\U0001f32b\ufe0f"),
    51: ("\u5c0f\u6bdb\u6bdb\u96e8", "\U0001f327\ufe0f"),
    53: ("\u6bdb\u6bdb\u96e8", "\U0001f327\ufe0f"),
    55: ("\u5927\u6bdb\u6bdb\u96e8", "\U0001f327\ufe0f"),
    56: ("\u51bb\u6bdb\u6bdb\u96e8", "\U0001f327\ufe0f"),
    57: ("\u51bb\u6bdb\u6bdb\u96e8", "\U0001f327\ufe0f"),
    61: ("\u5c0f\u96e8", "\U0001f327\ufe0f"),
    63: ("\u4e2d\u96e8", "\U0001f327\ufe0f"),
    65: ("\u5927\u96e8", "\U0001f327\ufe0f"),
    66: ("\u51bb\u96e8", "\U0001f327\ufe0f"),
    67: ("\u51bb\u96e8", "\U0001f327\ufe0f"),
    71: ("\u5c0f\u96ea", "\u2744\ufe0f"),
    73: ("\u4e2d\u96ea", "\u2744\ufe0f"),
    75: ("\u5927\u96ea", "\u2744\ufe0f"),
    77: ("\u96ea\u7c92", "\u2744\ufe0f"),
    80: ("\u9635\u96e8", "\U0001f327\ufe0f"),
    81: ("\u5f3a\u9635\u96e8", "\U0001f327\ufe0f"),
    82: ("\u66b4\u96e8", "\U0001f327\ufe0f"),
    85: ("\u9635\u96ea", "\u2744\ufe0f"),
    86: ("\u5f3a\u9635\u96ea", "\u2744\ufe0f"),
    95: ("\u96f7\u66b4", "\u26c8\ufe0f"),
    # Open-Meteo 仅在中欧提供冰雹预报；国内不把 96/99 展示成确定冰雹。
    96: ("\u5f3a\u5bf9\u6d41\u96f7\u96e8", "\u26c8\ufe0f"),
    99: ("\u5f3a\u5bf9\u6d41\u96f7\u96e8", "\u26c8\ufe0f"),
}
WEATHER_CAMPUSES = {
    "siping": {"name": "四平路校区", "latitude": 31.28294, "longitude": 121.501489},
    "jiading": {"name": "嘉定校区", "latitude": 31.28984, "longitude": 121.17712},
}
WEATHER_CACHE_TTL_SECONDS = 15 * 60
_weather_cache: dict[str, dict] = {}
_weather_locks = {campus: threading.Lock() for campus in WEATHER_CAMPUSES}



def _weather_url_for(campus: str) -> str:
    location = WEATHER_CAMPUSES[campus]
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={location['latitude']}&longitude={location['longitude']}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
        "&timezone=Asia/Shanghai"
    )


def get_greeting_info(dt=None):
    if dt is None:
        dt = datetime.now(CST)
    hour = dt.hour
    is_night = (hour >= 19 or hour < 5)
    if 0 <= hour < 5:
        return "夜深了", "🌙", is_night
    elif 5 <= hour < 9:
        return "早上好", "🌅", is_night
    elif 9 <= hour < 12:
        return "上午好", "☀️", is_night
    elif 12 <= hour < 14:
        return "中午好", "☀️", is_night
    elif 14 <= hour < 19:
        return "下午好", "🌤️", is_night
    else:
        return "晚上好", "🌙", is_night


@app.route("/")
def index():
    _refresh_session_activity()
    greeting_text, greeting_icon, is_night = get_greeting_info()
    return render_template(
        "index.html",
        username=session.get("username"),
        greeting_text=greeting_text,
        greeting_icon=greeting_icon,
        is_night=is_night,
        icp_number=settings.ICP_NUMBER,
        apple_calendar_enabled=settings.APPLE_CALENDAR_ENABLED,
    )


@app.route("/component-lab")
def component_lab():
    """Render the isolated visual component laboratory for authenticated users."""
    return render_template("component_lab.html")


@app.route("/api/dashboard/preferences", methods=["GET", "PUT"])
def api_dashboard_preferences():
    """Read or update account-scoped overview display preferences."""
    username = session["username"]
    if request.method == "GET":
        return jsonify({"ok": True, **dashboard_preferences.load(username)})

    data = read_json_request()
    visible_sources = data.get("visible_todo_sources") if data else None
    if (
        not isinstance(visible_sources, list)
        or any(
            not isinstance(source, str) or source not in dashboard_preferences.TODO_SOURCES
            for source in visible_sources
        )
        or len(visible_sources) != len(set(visible_sources))
    ):
        return api_error(
            "visible_todo_sources_invalid",
            "待办来源显示设置无效",
            400,
        )
    preferences = dashboard_preferences.save_visible_todo_sources(username, visible_sources)
    return jsonify({"ok": True, **preferences})


@app.route("/login/<platform>")
def login_page(platform):
    if platform not in ("canvas", "haoke", "zhixuemeng", "zhihuishu", "ketangpai", "tongjioj"):
        return "Not Found", 404
    return render_template(f"login_{platform}.html", username=session.get("username"))


@app.route("/api/apple-calendar/subscription", methods=["POST", "DELETE"])
def api_apple_calendar_subscription():
    if not settings.APPLE_CALENDAR_ENABLED:
        abort(404)
    username = session["username"]
    if request.method == "DELETE":
        return jsonify({"ok": apple_calendar.revoke_token(username)})

    token = apple_calendar.create_token(username)
    feeds = []
    for cat_id in ("courses", "assignments", "projects", "schedule", "all"):
        cat_meta = CALENDAR_CATEGORIES[cat_id]
        path = f"/calendar/{token}.ics" if cat_id == "all" else f"/calendar/{token}/{cat_id}.ics"
        feeds.append({
            "id": cat_id,
            "name": cat_meta["name"],
            "color": cat_meta["color"],
            "description": cat_meta["description"],
            "path": path,
        })
    return jsonify({
        "ok": True,
        "token": token,
        "path": f"/calendar/{token}.ics",
        "feeds": feeds,
    })


@app.route("/calendar/<token>.ics")
def calendar_subscription(token):
    if not settings.APPLE_CALENDAR_ENABLED:
        abort(404)
    username = apple_calendar.username_for_token(token)
    account = auth.account_metadata(username) if username else None
    if not username or (not app.testing and (not account or account.get("status") != "active")):
        return "Not Found", 404
    raw_cat = request.args.get("category", "all").strip().lower()
    cat_id = CATEGORY_ALIASES.get(raw_cat)
    if not cat_id or cat_id not in CALENDAR_CATEGORIES:
        return "Not Found", 404
    cat_meta = CALENDAR_CATEGORIES[cat_id]
    response = app.response_class(
        apple_calendar.build_calendar(
            username,
            _calendar_items(username, category=cat_id),
            datetime.now(CST),
            cal_name=cat_meta["name"],
            cal_color=cat_meta["color"],
        ),
        content_type="text/calendar; charset=utf-8",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route("/calendar/<token>/<category>.ics")
def calendar_category_subscription(token, category):
    if not settings.APPLE_CALENDAR_ENABLED:
        abort(404)
    username = apple_calendar.username_for_token(token)
    account = auth.account_metadata(username) if username else None
    if not username or (not app.testing and (not account or account.get("status") != "active")):
        return "Not Found", 404
    cat_id = CATEGORY_ALIASES.get((category or "").strip().lower())
    if not cat_id or cat_id not in CALENDAR_CATEGORIES:
        return "Not Found", 404
    cat_meta = CALENDAR_CATEGORIES[cat_id]
    response = app.response_class(
        apple_calendar.build_calendar(
            username,
            _calendar_items(username, category=cat_id),
            datetime.now(CST),
            cal_name=cat_meta["name"],
            cal_color=cat_meta["color"],
        ),
        content_type="text/calendar; charset=utf-8",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


# ---- Site-wide account system ----


@app.route("/login")
def site_login_page():
    if session.get("username"):
        return redirect("/")
    return render_template("auth_login.html", icp_number=settings.ICP_NUMBER)


@app.route("/register")
def site_register_page():
    if session.get("username"):
        return redirect("/")
    return render_template("auth_register.html", icp_number=settings.ICP_NUMBER, registration_enabled=settings.REGISTRATION_ENABLED)


@app.route("/privacy")
def site_privacy_page():
    return render_template(
        "privacy.html",
        logged_in=bool(session.get("username")),
        icp_number=settings.ICP_NUMBER,
    )


@app.route("/welcome")
def site_welcome_page():
    if session.get("username"):
        return redirect("/")
    return render_template("auth_login.html", icp_number=settings.ICP_NUMBER)


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    if not settings.REGISTRATION_ENABLED:
        return api_error("registration_closed", "暂时停止新账户注册，已有账户仍可登录。", 403)
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    # Rate limit by IP to prevent creating unlimited accounts by rotating usernames
    client_ip = _request_ip()
    skip_ip_limit = app.config.get("TESTING") and client_ip in ("127.0.0.1", "::1", "localhost")
    if not skip_ip_limit:
        allowed_ip, retry_after_ip = _check_rate_limit(
            "auth-register-ip", client_ip, REGISTER_RATE_LIMIT_ATTEMPTS, REGISTER_RATE_LIMIT_SECONDS
        )
        if not allowed_ip:
            return _rate_limited_response(retry_after_ip)
    allowed, retry_after = _check_rate_limit(
        "auth-register", username, REGISTER_RATE_LIMIT_ATTEMPTS, REGISTER_RATE_LIMIT_SECONDS
    )
    if not allowed:
        return _rate_limited_response(retry_after)
    ok, error = auth.register(username, password)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    account_id, session_version = auth.session_identity(username)
    csrf_token = session.get(_CSRF_SESSION_KEY)
    session.clear()
    session.update(username=username, account_id=account_id, session_version=session_version)
    if csrf_token:
        session[_CSRF_SESSION_KEY] = csrf_token
    _refresh_session_activity(force=True)
    return jsonify({"ok": True})


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    allowed, retry_after = _check_rate_limit(
        "auth-login", username, LOGIN_RATE_LIMIT_ATTEMPTS, LOGIN_RATE_LIMIT_SECONDS
    )
    if not allowed:
        return _rate_limited_response(retry_after)
    identity = auth.verify_login(username, password)
    if not identity:
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    current_identity = auth.session_identity(username)
    if (
        not current_identity
        or not isinstance(identity, dict)
        or (
            identity.get("account_id") != current_identity[0]
            or identity.get("session_version") != current_identity[1]
        )
    ):
        return jsonify({"ok": False, "error": "账户状态已变更，请重新登录"}), 401
    account_id, session_version = identity["account_id"], identity["session_version"]
    csrf_token = session.get(_CSRF_SESSION_KEY)
    session.clear()
    session.update(username=username, account_id=account_id, session_version=session_version)
    if csrf_token:
        session[_CSRF_SESSION_KEY] = csrf_token
    _refresh_session_activity(force=True)
    return jsonify({"ok": True})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session/activity", methods=["POST"])
def api_session_activity():
    return jsonify({"ok": True, "refreshed": _refresh_session_activity()})


@app.route("/reset-password")
def site_password_reset_page():
    return render_template("auth_reset_password.html", icp_number=settings.ICP_NUMBER)


@app.route("/api/auth/reset-password", methods=["POST"])
def api_auth_password_reset():
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    username = (data.get("username") or "").strip()
    ok, error = auth.reset_password(username, data.get("token") or "", data.get("password") or "")
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/account", methods=["GET", "DELETE"])
def api_account():
    username = session["username"]
    account_id = session.get("account_id")
    session_version = session.get("session_version")
    if request.method == "GET":
        metadata = auth.account_metadata(username)
        if not metadata:
            return api_error("account_missing", "账号不存在", 404)
        return jsonify({"ok": True, "account": metadata})

    data = read_json_request()
    if data is None:
        return invalid_request_response()
    password = data.get("password") or ""
    confirmation = data.get("confirmation") or ""
    if not password or not confirmation:
        return api_error("invalid_request", "请提供密码和确认文字", 400)
    if confirmation != auth.DELETE_CONFIRMATION:
        return api_error("invalid_confirmation", f"请准确输入“{auth.DELETE_CONFIRMATION}”", 400)

    def cleanup_resources():
        zhihuishu_login_sessions.stop_session(username)
        tongji_login_sessions.stop_session(username)
        try:
            zhixuemeng_client = __import__("zhixuemeng_client")
            zhixuemeng_client.logout(username)
        except Exception:
            logger.warning("Could not clear in-memory 智学盟 state for account deletion")
        try:
            ktp_logout(username)
        except Exception:
            logger.warning("Could not clear in-memory 课堂派 state for account deletion")
        try:
            tjoj_logout(username)
        except Exception:
            logger.warning("Could not clear in-memory 同济OJ state for account deletion")

    ok, error = auth.delete_account(
        username,
        password,
        confirmation,
        expected_account_id=account_id,
        expected_session_version=session_version,
        before_delete=cleanup_resources,
    )
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    session.clear()
    return jsonify({"ok": True, "cleanup_pending": bool(error), "message": error})


@app.route("/api/account/sessions/revoke-others", methods=["POST"])
def api_revoke_other_sessions():
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    ok, session_version = auth.revoke_other_sessions(session["username"], data.get("password") or "")
    if not ok:
        return jsonify({"ok": False, "error": "当前网站密码错误"}), 401
    # Keep this browser's identity aligned with the incremented account record.
    # The current CSRF token deliberately remains unchanged.
    session["session_version"] = session_version
    return jsonify({"ok": True, "message": "其他设备的登录状态已失效"})


@app.route("/api/operations/<token>")
def api_operation_status(token):
    result, status = task_status(token, session["username"])
    return jsonify(result), status


@app.after_request
def _record_request_end(response):
    started = g.pop("metrics_started", None)
    if started is not None:
        runtime_metrics.request_finished(request.endpoint or "unknown", request.method,
                                         response.status_code, time.monotonic() - started)
    return response


@app.route("/api/diagnostics/runtime")
def api_runtime_diagnostics():
    from system_monitor import system_snapshot
    from login_capacity import capacity_snapshot
    return jsonify({"ok": True, "system": system_snapshot(DATA_DIR), "web": runtime_metrics.web_snapshot(),
                    "sync": http_sync.snapshot(), "browsers": capacity_snapshot(DATA_DIR)})


@app.route("/api/clock")
def api_clock():
    now = datetime.now(CST)
    weekdays = [
        "\u661f\u671f\u4e00",
        "\u661f\u671f\u4e8c",
        "\u661f\u671f\u4e09",
        "\u661f\u671f\u56db",
        "\u661f\u671f\u4e94",
        "\u661f\u671f\u516d",
        "\u661f\u671f\u65e5",
    ]
    return jsonify({
        "time": now.strftime("%H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "weekday": weekdays[now.weekday()],
        "iso": now.isoformat(),
    })


def _refresh_weather(campus):
    try:
        response = requests.get(_weather_url_for(campus), timeout=5)
        current = response.json().get("current", {})
        code = current.get("weather_code", -1)
        desc, emoji = WMO_CODES.get(code, (f"未知({code})", "?"))
        payload = {"ok": True, "temperature": current.get("temperature_2m"),
                   "humidity": current.get("relative_humidity_2m"), "campus": campus,
                   "campus_name": WEATHER_CAMPUSES[campus]["name"], "weather_code": code,
                   "weather_desc": desc, "weather_emoji": emoji}
        _weather_cache[campus] = {"data": payload, "cached_at": time.time()}
        return payload
    except Exception:
        cached = _weather_cache.get(campus, {})
        _weather_cache[campus] = {**cached, "retry_at": time.time() + 60}
        return {"ok": False}


@app.route("/api/weather")
def api_weather():
    campus = request.args.get("campus", "siping")
    if campus not in WEATHER_CAMPUSES:
        return api_error("weather_campus_invalid", "校区无效", 400)
    cached = _weather_cache.get(campus, {})
    if (time.time() - cached.get("cached_at", 0) >= WEATHER_CACHE_TTL_SECONDS
            and time.time() >= cached.get("retry_at", 0)):
        http_sync.submit_http_sync("__system__", "weather", lambda: _refresh_weather(campus),
                                   job_type=campus, system=True)
    result = dict(cached.get("data") or {"ok": False, "error": "天气暂不可用"})
    result["pending"] = http_sync.is_refreshing("__system__", "weather", campus)
    return jsonify(result)


@app.route("/api/config", methods=["GET", "POST", "DELETE"])
def api_config():
    username = session["username"]
    if request.method == "DELETE":
        remove_feed_url(username)
        platform_sync.mark_disconnected(username, "canvas", _platform_cache_path(username, "canvas").exists())
        return jsonify({"ok": True, "disconnected": True})
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        url = (data.get("calendar_feed_url") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "URL 不能为空"}), 400
        ok, error = save_feed_url(username, url)
        if not ok:
            return jsonify({"ok": False, "error": error}), 400
        platform_sync.mark_connected(username, "canvas")
        return jsonify({"ok": True})

    return jsonify({"ok": True, "has_feed": has_feed_url(username)})


@app.route("/api/canvas/todos")
def api_canvas_todos():
    username = session["username"]
    cache_path = _platform_cache_path(username, "canvas")
    disconnected = platform_sync.get(username, "canvas")["connection_state"] == "disconnected"
    if disconnected and not has_feed_url(username) and cache_path.exists():
        result = {"ok": True, "data": canvas_cached_items(username), "cached": True, "disconnected": True, "need_setup": True}
    elif not has_feed_url(username):
        result = {"ok": False, "error": "请先设置日历馈送源 URL", "data": [], "need_setup": True}
    else:
        cache_only = request.args.get("cache_only") == "1"
        force_refresh = request.args.get("refresh") == "1"
        cached_result = get_canvas_cached_todos(username)
        has_cache = cached_result.get("has_cache", False)
        stale = cached_result.get("stale", True)

        if not cache_only and (force_refresh or not has_cache or stale):
            start_canvas_background_refresh(username)

        if cached_result.get("ok"):
            result = cached_result
        else:
            result = {"ok": True, "data": [], "cached": True, "stale": True, "has_cache": False}

    state = load_state(username)
    result = build_platform_todos_response(
        result,
        state,
        expire_hidden=lambda expired_ids: delete_canvas_expired_hidden(username, expired_ids),
        expire_completed=lambda items, now: delete_canvas_expired_completed(username, items, now),
        now=datetime.now(CST),
    )
    result = attach_subtasks(username, "canvas", result)
    state_name = "connected" if has_feed_url(username) else platform_sync.get(username, "canvas")["connection_state"]
    refreshing = is_canvas_refreshing(username)
    result["refreshing"] = refreshing
    return jsonify(_attach_sync(result, "canvas", connection_state=state_name, refreshing=refreshing))


@app.route("/api/canvas/state", methods=["GET", "POST"])
def api_canvas_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete") or item_id is None:
            return jsonify({"ok": False, "error": "无效操作"}), 400
        state = update_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_state(username)})


# ---- Haoke Platform ----


@app.route("/api/haoke/config", methods=["GET", "POST", "DELETE"])
def api_haoke_config():
    username = session["username"]
    if request.method == "DELETE":
        clear_haoke_credentials(username)
        platform_sync.mark_disconnected(username, "haoke", _platform_cache_path(username, "haoke").exists())
        return jsonify({"ok": True, "disconnected": True})
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        haoke_username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        if not haoke_username or not password:
            return api_error("haoke_credentials_required", "username and password required")
        save_haoke_credentials(username, haoke_username, password)
        platform_sync.mark_connected(username, "haoke")
        return jsonify({"ok": True})

    return jsonify({"ok": True, "has_credentials": has_haoke_credentials(username)})


@app.route("/api/haoke/todos")
def api_haoke_todos():
    username = session["username"]
    result = None
    has_credentials = has_haoke_credentials(username)
    cache_only = request.args.get("cache_only") == "1"
    if has_credentials:
        result = get_haoke_cached_todos(username)
        if result is not None:
            result = dict(result)
            is_stale = bool(result.get("stale"))
            if not cache_only and (is_stale or request.args.get("refresh") == "1"):
                start_haoke_background_refresh(username)
                result = dict(get_haoke_cached_todos(username) or result)
    if result is None:
        if not has_credentials and _platform_cache_path(username, "haoke").exists():
            result = get_haoke_cached_todos(username) or {"ok": True, "data": []}
            result = dict(result)
            result.update(disconnected=True, need_setup=True, refreshing=False)
        elif cache_only:
            result = {"ok": True, "data": [], "cached": True, "need_setup": not has_credentials,
                      "refreshing": is_haoke_refreshing(username), "has_cache": False}
        elif has_credentials:
            start_haoke_background_refresh(username)
            result = {
                "ok": True,
                "data": [],
                "cached": True,
                "stale": True,
                "has_cache": False,
                "refreshing": is_haoke_refreshing(username),
            }
        else:
            result = {"ok": False, "error": "未配置好课账号", "need_setup": True, "data": []}
    result = dict(result)
    # Reading the cache snapshot happens before the refresh is submitted, so the
    # polling flag must be re-read afterwards; otherwise a stale cache answers
    # "not refreshing" and the browser stops polling before the result lands.
    result["refreshing"] = is_haoke_refreshing(username)
    result = _with_default_error_code(result, _haoke_default_error_code(result))
    state = load_haoke_state(username)
    result = build_platform_todos_response(
        result,
        state,
        expire_hidden=lambda expired_ids: delete_haoke_expired_hidden(username, expired_ids),
        expire_completed=lambda items, now: delete_haoke_expired_completed(username, items, now),
        now=datetime.now(CST),
    )
    result = attach_subtasks(username, "haoke", result)
    connection_state = "connected" if has_credentials else platform_sync.get(username, "haoke")["connection_state"]
    return jsonify(_attach_sync(result, "haoke", connection_state=connection_state, refreshing=result.get("refreshing", False)))


@app.route("/api/haoke/state", methods=["GET", "POST"])
def api_haoke_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete") or item_id is None:
            return jsonify({"ok": False, "error": "无效操作"}), 400
        state = update_haoke_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_haoke_state(username)})


# ---- Zhixuemeng Platform ----


@app.route("/api/zhixuemeng/send-sms", methods=["POST"])
@background_operation("zhixuemeng", "api_zxm_send_sms")
def api_zxm_send_sms():
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"ok": False, "error": "phone required"}), 400
    allowed, retry_after = _check_rate_limit(
        "zhixuemeng-send-sms", phone, SMS_RATE_LIMIT_ATTEMPTS, SMS_RATE_LIMIT_SECONDS
    )
    if not allowed:
        return _rate_limited_response(retry_after)
    result = send_sms(phone)
    return jsonify(result)


@app.route("/api/zhixuemeng/login", methods=["POST"])
@background_operation("zhixuemeng", "api_zxm_login")
def api_zxm_login():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    phone = (data.get("phone") or "").strip()
    captcha = (data.get("captcha") or "").strip()
    if not phone or not captcha:
        return jsonify({"ok": False, "error": "phone and captcha required"}), 400
    result = phone_login(username, phone, captcha)
    if result.get("ok"):
        platform_sync.mark_connected(username, "zhixuemeng")
    return jsonify(result)


@app.route("/api/zhixuemeng/login-password", methods=["POST"])
@background_operation("zhixuemeng", "api_zxm_login_password")
def api_zxm_login_password():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    zxm_username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not zxm_username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    result = password_login(username, zxm_username, password)
    if result.get("ok"):
        platform_sync.mark_connected(username, "zhixuemeng")
    return jsonify(result)


@app.route("/api/zhixuemeng/logout", methods=["POST"])
def api_zxm_logout():
    username = session["username"]
    zxm_logout(username)
    platform_sync.mark_disconnected(username, "zhixuemeng", _platform_cache_path(username, "zhixuemeng").exists())
    return jsonify({"ok": True})


@app.route("/api/zhixuemeng/config")
def api_zxm_config():
    username = session["username"]
    has_token = has_zxm_token(username)
    result = {"ok": True, "has_token": has_token}
    if has_token:
        cached = platform_http.cached_assignments(username, "zhixuemeng")
        result["courses"] = cached["courses"]
        if cached["stale"]:
            platform_http.start_refresh(username, "zhixuemeng")
        result["refreshing"] = http_sync.is_refreshing(username, "zhixuemeng")
        result["selected_course"] = get_selected_course(username)
    return jsonify(result)


@app.route("/api/zhixuemeng/course", methods=["POST"])
def api_zxm_course():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    course_code = (data.get("course_code") or "").strip()
    save_selected_course(username, course_code)
    return jsonify({"ok": True})


@app.route("/api/zhixuemeng/todos")
def api_zxm_todos():
    username = session["username"]
    course_code = request.args.get("course_code", "").strip() or get_selected_course(username)
    result = platform_http.cached_assignments(username, "zhixuemeng", course_code)
    if (request.args.get("cache_only") != "1" and result["stale"] and has_zxm_token(username)) or request.args.get("refresh") == "1":
        platform_http.start_refresh(username, "zhixuemeng")
    state = load_zxm_state(username)
    result = build_platform_todos_response(
        result,
        state,
        items_key="items",
        expire_hidden=lambda expired_ids: delete_zxm_expired_hidden(username, expired_ids),
        expire_completed=lambda items, now: delete_zxm_expired_completed(username, items, now),
        now=datetime.now(CST),
    )
    result = attach_subtasks(username, "zhixuemeng", result)
    connection_state = "connected" if has_zxm_token(username) else platform_sync.get(username, "zhixuemeng")["connection_state"]
    return jsonify(_attach_sync(result, "zhixuemeng", connection_state=connection_state,
                                      refreshing=http_sync.is_refreshing(username, "zhixuemeng")))


@app.route("/api/zhixuemeng/state", methods=["GET", "POST"])
def api_zxm_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete") or item_id is None:
            return jsonify({"ok": False, "error": "无效操作"}), 400
        state = update_zxm_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_zxm_state(username)})


# ---- Ketangpai Platform ----


@app.route("/api/ketangpai/send-sms", methods=["POST"])
@background_operation("ketangpai", "api_ktp_send_sms")
def api_ktp_send_sms():
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    phone = (data.get("phone") or "").strip()
    verify = (data.get("verify") or "").strip()
    sessionid = (data.get("sessionid") or "").strip()
    if not phone:
        return jsonify({"ok": False, "error": "phone required"}), 400
    allowed, retry_after = _check_rate_limit(
        "ketangpai-send-sms", phone, SMS_RATE_LIMIT_ATTEMPTS, SMS_RATE_LIMIT_SECONDS
    )
    if not allowed:
        return _rate_limited_response(retry_after)
    result = ktp_send_sms(phone, verify=verify, sessionid=sessionid)
    return jsonify(result)


@app.route("/api/ketangpai/figure-code")
@background_operation("ketangpai", "api_ktp_figure_code")
def api_ktp_figure_code():
    result = ketangpai_client.get_figure_code()
    return jsonify(result)


@app.route("/api/ketangpai/login", methods=["POST"])
@background_operation("ketangpai", "api_ktp_login")
def api_ktp_login():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    phone = (data.get("phone") or "").strip()
    code = (data.get("code") or "").strip()
    if not phone or not code:
        return jsonify({"ok": False, "error": "phone and code required"}), 400
    result = ktp_phone_login(username, phone, code)
    if result.get("ok"):
        platform_sync.mark_connected(username, "ketangpai")
    return jsonify(result)


@app.route("/api/ketangpai/login-password", methods=["POST"])
@background_operation("ketangpai", "api_ktp_login_password")
def api_ktp_login_password():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    account = (data.get("account") or data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not account or not password:
        return jsonify({"ok": False, "error": "account and password required"}), 400
    result = ktp_password_login(username, account, password)
    if result.get("ok"):
        platform_sync.mark_connected(username, "ketangpai")
    return jsonify(result)


@app.route("/api/ketangpai/logout", methods=["POST"])
def api_ktp_logout():
    username = session["username"]
    ktp_logout(username)
    platform_sync.mark_disconnected(username, "ketangpai", _platform_cache_path(username, "ketangpai").exists())
    return jsonify({"ok": True})


@app.route("/api/ketangpai/config")
def api_ktp_config():
    username = session["username"]
    has_token = has_ktp_token(username)
    result = {"ok": True, "has_token": has_token}
    if has_token:
        cached = platform_http.cached_assignments(username, "ketangpai")
        result["courses"] = cached["courses"]
        if cached["stale"]:
            platform_http.start_refresh(username, "ketangpai")
        result["refreshing"] = http_sync.is_refreshing(username, "ketangpai")
    return jsonify(result)


@app.route("/api/ketangpai/todos")
def api_ktp_todos():
    username = session["username"]
    course_id = request.args.get("course_id", "").strip()
    result = platform_http.cached_assignments(username, "ketangpai", course_id)
    if (request.args.get("cache_only") != "1" and result["stale"] and has_ktp_token(username)) or request.args.get("refresh") == "1":
        platform_http.start_refresh(username, "ketangpai")
    state = load_ktp_state(username)
    result = build_platform_todos_response(
        result,
        state,
        items_key="items",
        expire_hidden=lambda expired_ids: delete_ktp_expired_hidden(username, expired_ids),
        expire_completed=lambda items, now: delete_ktp_expired_completed(username, items, now),
        now=datetime.now(CST),
    )
    result = attach_subtasks(username, "ketangpai", result)
    connection_state = "connected" if has_ktp_token(username) else platform_sync.get(username, "ketangpai")["connection_state"]
    return jsonify(_attach_sync(result, "ketangpai", connection_state=connection_state,
                                      refreshing=http_sync.is_refreshing(username, "ketangpai")))


@app.route("/api/ketangpai/state", methods=["GET", "POST"])
def api_ktp_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete") or item_id is None:
            return invalid_request_response()
        state = update_ktp_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_ktp_state(username)})


# ---- Tongji OJ Platform (同济大学竞教融合实训平台) ----


@app.route("/api/tongjioj/login", methods=["POST"])
@app.route("/api/tongjioj/login-iam", methods=["POST"])
@background_operation("tongjioj", "api_tjoj_login_iam")
def api_tjoj_login_iam():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    student_id = (data.get("username") or data.get("student_id") or data.get("account") or "").strip()
    password = (data.get("password") or "").strip()
    if not student_id or not password:
        return jsonify({"ok": False, "error": "请输入学号/工号和统一身份认证密码"}), 400
    result = tjoj_iam_login(username, student_id, password)
    if result.get("ok"):
        platform_sync.mark_connected(username, "tongjioj")
    return jsonify(result)


@app.route("/api/tongjioj/iam-send-code", methods=["POST"])
@background_operation("tongjioj", "api_tjoj_iam_send_code")
def api_tjoj_iam_send_code():
    username = session["username"]
    data = read_json_request() or {}
    auth_type = (data.get("type") or "sms").strip().lower()
    allowed, retry_after = _check_rate_limit(
        "tongjioj-iam-send-code", username, SMS_RATE_LIMIT_ATTEMPTS, SMS_RATE_LIMIT_SECONDS
    )
    if not allowed:
        return _rate_limited_response(retry_after)
    result = tjoj_iam_send_second_auth_code(username, auth_type=auth_type)
    return jsonify(result)


@app.route("/api/tongjioj/iam-verify-code", methods=["POST"])
@background_operation("tongjioj", "api_tjoj_iam_verify_code")
def api_tjoj_iam_verify_code():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    code = (data.get("code") or "").strip()
    auth_type = (data.get("type") or "sms").strip().lower()
    if not code:
        return jsonify({"ok": False, "error": "请输入验证码"}), 400
    result = tjoj_iam_verify_second_auth_code(username, code=code, auth_type=auth_type)
    if result.get("ok"):
        platform_sync.mark_connected(username, "tongjioj")
    return jsonify(result)


@app.route("/api/tongjioj/login-local", methods=["POST"])
@background_operation("tongjioj", "api_tjoj_login_local")
def api_tjoj_login_local():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    account = (data.get("username") or data.get("account") or "").strip()
    password = (data.get("password") or "").strip()
    if not account or not password:
        return jsonify({"ok": False, "error": "请输入实训平台用户名和密码"}), 400
    result = tjoj_local_login(username, account, password)
    if result.get("ok"):
        platform_sync.mark_connected(username, "tongjioj")
    return jsonify(result)


@app.route("/api/tongjioj/logout", methods=["POST"])
def api_tjoj_logout():
    username = session["username"]
    tjoj_logout(username)
    platform_sync.mark_disconnected(username, "tongjioj", _platform_cache_path(username, "tongjioj").exists())
    return jsonify({"ok": True})


@app.route("/api/tongjioj/config")
def api_tjoj_config():
    username = session["username"]
    has_creds = has_tjoj_credentials(username)
    result = {
        "ok": True,
        "has_credentials": has_creds,
        "has_token": has_creds,
        "selected_course": get_tjoj_selected_course(username) or "",
    }
    if has_creds:
        # Configuration reads must not duplicate the slow todo synchronization.
        result["courses"] = tongji_oj_client.get_saved_courses(username)
    return jsonify(result)


@app.route("/api/tongjioj/course", methods=["POST"])
def api_tjoj_course():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    course_id = (data.get("course_id") or "").strip()
    set_tjoj_selected_course(username, course_id)
    return jsonify({"ok": True, "selected_course": course_id})


@app.route("/api/tongjioj/todos")
def api_tjoj_todos():
    username = session["username"]
    course_id = request.args.get("course_id")
    if course_id is not None:
        course_id = course_id.strip() or None
    had_creds = has_tjoj_credentials(username)
    cache_only = request.args.get("cache_only") == "1"
    result = tongji_oj_client.get_cached_assignments(username, course_id=course_id)
    if had_creds and not cache_only and (request.args.get("refresh") == "1" or result.get("stale")):
        tongji_oj_client.start_background_refresh(username)
        result = tongji_oj_client.get_cached_assignments(username, course_id=course_id)
    state = load_tjoj_state(username)
    result = build_platform_todos_response(
        result,
        state,
        items_key="items",
        expire_hidden=lambda expired_ids: delete_tjoj_expired_hidden(username, expired_ids),
        expire_completed=lambda items, now: delete_tjoj_expired_completed(username, items, now),
        now=datetime.now(CST),
    )
    result = attach_subtasks(username, "tongjioj", result)
    connection_state = "connected" if has_tjoj_credentials(username) else platform_sync.get(username, "tongjioj")["connection_state"]
    return jsonify(_attach_sync(result, "tongjioj", connection_state=connection_state, refreshing=result.get("refreshing", False)))


@app.route("/api/tongjioj/state", methods=["GET", "POST"])
def api_tjoj_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete") or item_id is None:
            return invalid_request_response()
        state = update_tjoj_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_tjoj_state(username)})


# ---- Zhihuishu Platform ----


@app.route("/api/zhihuishu/config", methods=["GET", "DELETE"])
def api_zhihuishu_config():
    username = session["username"]
    if request.method == "DELETE":
        zhihuishu_login_sessions.stop_session(username)
        profile = user_dir(username) / "zhihuishu_chromium_profile"
        import shutil
        shutil.rmtree(profile, ignore_errors=True)
        status = zhihuishu_store.save_status(username, {"session": "disconnected", "last_error": "已断开智慧树连接"})
        platform_sync.mark_disconnected(username, "zhihuishu", _platform_cache_path(username, "zhihuishu").exists())
        return jsonify({"ok": True, "disconnected": True, "status": status})
    status = zhihuishu_store.load_status(username)
    login_session = zhihuishu_login_sessions.load_session(username)
    session_summary = {"active": False}
    if login_session:
        session_summary = {
            "active": True,
            "created_at": login_session.get("created_at"),
            "expires_at": login_session.get("expires_at"),
            "port": login_session.get("port"),
        }
    return jsonify({"ok": True, "status": status, "login_session": session_summary})


@app.route("/api/zhihuishu/todos")
def api_zhihuishu_todos():
    username = session["username"]
    status = zhihuishu_store.load_status(username)
    state = zhihuishu_store.load_state(username)
    cache = zhihuishu_store.load_cache(username)

    if status.get("session") in ("not_logged_in", "need_relogin") and not cache["items"]:
        result = {
            "ok": False,
            "need_setup": True,
            "status": status,
            "data": [],
            "hidden": state["hidden"],
            "highlighted": state["highlighted"],
            "deleted": state["deleted"],
        }
        state_name = "needs_reauth" if status.get("session") == "need_relogin" else platform_sync.get(username, "zhihuishu")["connection_state"]
        return jsonify(_attach_sync(result, "zhihuishu", connection_state=state_name))

    result = {
        "ok": True,
        "need_setup": status.get("session") in ("not_logged_in", "need_relogin"),
        "data": cache["items"],
        "stale": cache["stale"],
        "fetched_at": cache["fetched_at"],
        "status": status,
    }
    result = build_platform_todos_response(result, state, now=datetime.now(CST),
        expire_completed=lambda items, now: zhihuishu_store.delete_expired_completed(username, items, now))
    result = attach_subtasks(username, "zhihuishu", result)
    state_name = "connected" if status.get("session") == "active" else platform_sync.get(username, "zhihuishu")["connection_state"]
    return jsonify(_attach_sync(result, "zhihuishu", connection_state=state_name))


@app.route("/api/external-subtasks", methods=["PUT"])
def api_external_subtasks():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    source = data.get("source")
    item_id = data.get("item_id")
    subtasks = data.get("subtasks")
    if not source or item_id is None or not isinstance(subtasks, list):
        return jsonify({"ok": False, "error": "source, item_id and subtasks are required"}), 400
    try:
        saved = save_subtasks(username, source, item_id, subtasks)
        return jsonify({"ok": True, "subtasks": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/platform/<platform>/data", methods=["DELETE"])
def api_clear_platform_data(platform):
    """Irreversibly remove only one platform's credentials, cache and local state."""
    if platform not in platform_sync.PLATFORMS:
        abort(404)
    username = session["username"]
    directory = user_dir(username)
    # Read first so a malformed JSON file remains protected by the normal
    # fail-closed 503 path instead of being silently discarded.
    if platform == "canvas":
        remove_feed_url(username)
        paths = (directory / "canvas_cache.json", directory / "canvas_state.json")
    elif platform == "haoke":
        if (directory / "config.json").exists():
            read_json_file(directory / "config.json", {})
        clear_haoke_credentials(username)
        paths = (directory / "haoke_cache.json", directory / "haoke_state.json")
    elif platform == "zhixuemeng":
        if (directory / "config.json").exists():
            read_json_file(directory / "config.json", {})
        zxm_logout(username)
        paths = (directory / "zhixuemeng_cache.json", directory / "zhixuemeng_state.json")
    elif platform == "ketangpai":
        if (directory / "config.json").exists():
            read_json_file(directory / "config.json", {})
        ktp_logout(username)
        paths = (directory / "ketangpai_cache.json", directory / "ketangpai_state.json")
    elif platform == "tongjioj":
        if (directory / "config.json").exists():
            read_json_file(directory / "config.json", {})
        tjoj_logout(username)
        paths = (directory / "tongjioj_cache.json", directory / "tongjioj_state.json")
    else:
        zhihuishu_login_sessions.stop_session(username)
        profile = directory / "zhihuishu_chromium_profile"
        if profile.exists():
            shutil.rmtree(profile)
        paths = (
            directory / "zhihuishu_cache.json", directory / "zhihuishu_state.json",
            directory / "zhihuishu_status.json", directory / "zhihuishu_login_session.json",
        )
    for path in paths:
        _clear_json_file(path)
    platform_sync.mark_unconfigured(username, platform)
    return jsonify({"ok": True, "cleared": platform})


@app.route("/api/zhihuishu/state", methods=["GET", "POST"])
def api_zhihuishu_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "无效请求"}), 400
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete", "complete", "uncomplete") or item_id is None:
            return jsonify({"ok": False, "error": "无效操作"}), 400
        state = zhihuishu_store.update_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": zhihuishu_store.load_state(username)})


@app.route("/api/platform/<platform>/override", methods=["POST", "DELETE"])
def api_platform_override(platform):
    """Store a user-local display title/due override without touching source data."""
    stores = {
        "canvas": update_canvas_override,
        "haoke": update_haoke_override,
        "zhixuemeng": update_zxm_override,
        "zhihuishu": zhihuishu_store.update_override,
        "ketangpai": update_ktp_override,
        "tongjioj": update_tjoj_override,
    }
    update = stores.get(platform)
    if update is None:
        abort(404)
    data = read_json_request()
    if data is None or data.get("id") is None:
        return invalid_request_response()
    patch = {}
    if request.method == "POST":
        if "title" in data:
            title = (data.get("title") or "").strip()
            if not title or len(title) > 240:
                return invalid_request_response()
            patch["title"] = title
        if "due_ts" in data:
            raw_due = data.get("due_ts")
            if raw_due is not None and _parse_calendar_due(raw_due) is None:
                return invalid_request_response()
            patch["due_ts"] = raw_due
        if not patch:
            return invalid_request_response()
    state = update(session["username"], data["id"], patch, restore=request.method == "DELETE")
    return jsonify({"ok": True, "state": state})


@app.route("/api/zhihuishu/login-required", methods=["POST"])
def api_zhihuishu_login_required():
    username = session["username"]
    status = zhihuishu_store.save_status(username, {
        "session": "need_relogin",
        "last_error": "需要重新登录智慧树",
    })
    return jsonify({"ok": True, "status": status})


@app.route("/api/zhihuishu/login-session", methods=["POST"])
@background_operation("zhihuishu", "api_zhihuishu_login_session")
def api_zhihuishu_login_session():
    username = session["username"]
    try:
        login_session = zhihuishu_login_sessions.create_session(username)
    except LoginCapacityError as exc:
        return jsonify({"ok": False, "code": "login_capacity", "error": str(exc)}), 429, {"Retry-After": "30"}
    except Exception as e:
        logger.exception("Failed to create Zhihuishu login session")
        return jsonify({"ok": False, "error": f"启动登录窗口失败：{e}"}), 500
    return jsonify({
        "ok": True,
        "token": login_session["token"],
        "url": login_session["url"],
        "expires_at": login_session["expires_at"],
    })


@app.route("/api/zhihuishu/login-session", methods=["DELETE"])
def api_zhihuishu_login_session_stop_current():
    username = session["username"]
    stopped = zhihuishu_login_sessions.stop_session(username)
    return jsonify({"ok": stopped})


@app.route("/zhihuishu/session/<token>/")
def zhihuishu_login_session_page(token):
    login_session = zhihuishu_login_sessions.session_for_token(token)
    if not login_session or login_session.get("username") != session.get("username"):
        return "Not Found", 404
    port = login_session["port"]
    if not zhihuishu_login_sessions.validate_session(token, port):
        return "Not Found", 404
    vnc_path = f"zhs-vnc/{port}/{token}/websockify"
    return redirect(
        f"/zhs-vnc/{port}/{token}/vnc.html?"
        f"autoconnect=true&resize=scale&path={vnc_path}"
    )


@app.route("/api/zhihuishu/login-session-auth")
def api_zhihuishu_login_session_auth():
    token = request.args.get("token", "") or request.headers.get("X-Zhihuishu-Token", "")
    port = request.args.get("port", "") or request.headers.get("X-Zhihuishu-Port", "")
    if not zhihuishu_login_sessions.validate_session(token, port):
        return "", 401
    login_session = zhihuishu_login_sessions.session_for_token(token)
    if not login_session or login_session.get("username") != session.get("username"):
        return "", 401
    return "", 204


@app.route("/api/zhihuishu/login-session/<token>/complete", methods=["POST"])
@background_operation("zhihuishu", "api_zhihuishu_login_session_complete")
def api_zhihuishu_login_session_complete(token):
    username = session["username"]
    login_session = zhihuishu_login_sessions.session_for_token(token)
    if not login_session or login_session.get("username") != username:
        return jsonify({"ok": False, "error": "login session not found or expired"}), 404
    zhihuishu_login_sessions.stop_session(username, token)
    if not zhihuishu_worker.run_scheduled_cycle(username, force_fetch=True):
        return jsonify({"ok": False, "error": "login not detected yet"}), 400
    status = zhihuishu_store.load_status(username)
    return jsonify({"ok": True, "status": status})


@app.route("/api/zhihuishu/login-session/<token>", methods=["DELETE"])
def api_zhihuishu_login_session_stop(token):
    username = session["username"]
    stopped = zhihuishu_login_sessions.stop_session(username, token)
    return jsonify({"ok": stopped})


# ============================================================================
# Recurring Todos Endpoints (Web & Agent)
# ============================================================================


# ---- Course timetable and simple schedule items ----


# ---- School Term / Week ----


@app.route("/api/term")
def api_term():
    now = datetime.now(CST)
    term_label, week_num, semester_start = get_term_info(now)

    # Holiday detection from 1.tongji.edu.cn workbench calendar
    is_holiday, holiday_name = _check_today_holiday(now)

    return jsonify({
        "ok": True,
        "term": term_label,
        "week": week_num,
        "is_holiday": is_holiday,
        "holiday_name": holiday_name,
        "semester_start": semester_start,
    })


# ---- Holiday Detection (from 1.tongji.edu.cn workbench API) ----


# ---- Agent Integration (MCP & Agent Skills) ----


@app.route("/api/agent/token", methods=["GET"])
def api_agent_token_info():
    username = session["username"]
    return jsonify({"ok": True, **agent_auth.get_token_info(username)})


@app.route("/api/agent/token", methods=["POST"])
def api_agent_token_create():
    username = session["username"]
    data = read_json_request() or {}
    name = str(data.get("name", "")).strip()
    scopes = data.get("scopes")
    expires_in_days = data.get("expires_in_days")
    if len(name) > 80 or (scopes is not None and (not isinstance(scopes, list) or not scopes or any(scope not in agent_auth.VALID_SCOPES for scope in scopes))):
        return invalid_request_response()
    if expires_in_days is not None and (isinstance(expires_in_days, bool) or not isinstance(expires_in_days, int) or not 1 <= expires_in_days <= 3650):
        return invalid_request_response()
    try:
        token = agent_auth.create_token(username, name=name, scopes=scopes, expires_in_days=expires_in_days)
    except ValueError as exc:
        return api_error('token_limit', str(exc), 400)
    return jsonify({"ok": True, "token": token, **agent_auth.get_token_info(username)})


@app.route("/api/agent/token", methods=["DELETE"])
def api_agent_token_revoke():
    username = session["username"]
    data = read_json_request() or {}
    token_id = request.args.get("token_id") or data.get("token_id")
    revoked = agent_auth.revoke_token(username, token_id=token_id)
    return jsonify({"ok": True, "revoked": revoked, **agent_auth.get_token_info(username)})



@app.route("/api/agent/export/mcp-script")
def api_agent_export_mcp_script():
    mcp_path = Path(__file__).parent / "agent_mcp.py"
    if not mcp_path.exists():
        abort(404)
    content = mcp_path.read_text(encoding="utf-8")
    response = app.response_class(content, mimetype="text/x-python; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=canvas_mcp.py"
    return response


@app.route("/api/agent/export/mcp-bundle.zip")
def api_agent_export_mcp_bundle():
    mcp_path = Path(__file__).parent / "agent_mcp.py"
    if not mcp_path.exists():
        abort(404)
    mcp_code = mcp_path.read_text(encoding="utf-8")
    base_url = _get_external_base_url()

    claude_config = {
        "mcpServers": {
            "canvas-dashboard": {
                "command": "python",
                "args": ["canvas_mcp.py"],
                "env": {
                    "CANVAS_DASHBOARD_URL": base_url,
                    "CANVAS_DASHBOARD_TOKEN": "YOUR_TOKEN_HERE",
                },
            }
        }
    }
    cursor_config = {
        "mcpServers": {
            "canvas-dashboard": {
                "command": "python",
                "args": ["canvas_mcp.py"],
                "env": {
                    "CANVAS_DASHBOARD_URL": base_url,
                    "CANVAS_DASHBOARD_TOKEN": "YOUR_TOKEN_HERE",
                },
            }
        }
    }
    readme_content = f"""# Canvas Dashboard MCP 接入包

此压缩包内含将 Canvas Dashboard 连接至 Claude Desktop、Cursor、Cline、Windsurf 等 AI 助手的完整配置与脚本。

## 快速接入步骤（以 Claude Desktop 为例）

1. 将 `canvas_mcp.py` 复制到一个固定路径（例如 `C:\\Users\\<用户名>\\canvas_mcp.py` 或 `~/canvas_mcp.py`）。
   - 注意：若客户端未在解压目录下运行，请将 `claude_desktop_config.json` 或 `cursor_mcp.json` 中 `args` 里的 `canvas_mcp.py` 改为上述绝对路径。
2. 在 Canvas Dashboard 网页中生成你的专属 **Agent API Token**。
3. 打开客户端配置文件：
   - Claude Desktop (Windows): `%APPDATA%\\Claude\\claude_desktop_config.json`
   - Claude Desktop (macOS): `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Cursor: 项目或全局 `.cursor/mcp.json`
4. 合并配置并将 `YOUR_TOKEN_HERE` 替换为你的真实 Token。
5. 重启客户端即可开始使用！

## 常用提问示例
- “我今天有什么课？在哪个教室？”
- “今天有什么即将截止的作业？”
- “帮我添加一个明天晚上截止的数据库作业”
- “把高数作业标记为已完成”
"""
    readme_content += "\n## 写入规则\n" + WRITING_RULES + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("canvas_mcp.py", mcp_code)
        zf.writestr("claude_desktop_config.json", json.dumps(claude_config, indent=2, ensure_ascii=False))
        zf.writestr("cursor_mcp.json", json.dumps(cursor_config, indent=2, ensure_ascii=False))
        zf.writestr("README.md", readme_content)
    buf.seek(0)
    response = app.response_class(buf.getvalue(), mimetype="application/zip")
    response.headers["Content-Disposition"] = "attachment; filename=canvas-dashboard-mcp.zip"
    return response


SKILL_DIR = Path(__file__).parent / "skill"


@app.route("/skill/README.md")
@app.route("/skill")
@app.route("/skill/")
def api_skill_readme():
    readme_path = SKILL_DIR / "README.md"
    if not readme_path.exists():
        abort(404)
    content = readme_path.read_text(encoding="utf-8")
    base_url = _get_external_base_url()
    rendered = content.replace("{{ base_url }}", base_url)
    return app.response_class(rendered, mimetype="text/markdown; charset=utf-8")


@app.route("/skill/<path:filename>")
def api_skill_file(filename):
    safe_path = (SKILL_DIR / filename).resolve()
    if not safe_path.is_relative_to(SKILL_DIR.resolve()) or not safe_path.is_file():
        abort(404)

    mimetype = "text/plain; charset=utf-8"
    if filename.endswith(".md"):
        mimetype = "text/markdown; charset=utf-8"
    elif filename.endswith(".py"):
        mimetype = "text/x-python; charset=utf-8"
    elif filename.endswith(".sh"):
        mimetype = "text/x-shellscript; charset=utf-8"
    elif filename.endswith(".ps1"):
        mimetype = "text/plain; charset=utf-8"
    elif filename.endswith(".json"):
        mimetype = "application/json; charset=utf-8"

    content = safe_path.read_bytes()
    return app.response_class(content, mimetype=mimetype)


@app.route("/api/agent/export/skill-bundle.zip")
def api_agent_export_skill_bundle():
    base_url = _get_external_base_url()
    skill_file = SKILL_DIR / "SKILL.md"
    api_file = SKILL_DIR / "canvas_api.py"
    readme_file = SKILL_DIR / "README.md"

    if skill_file.exists():
        skill_content = skill_file.read_text(encoding="utf-8")
    else:
        skill_content = f"""---
name: canvas-dashboard
description: 通过用户授权管理 Canvas Dashboard 的责任待办、成长项目与时间安排。
---

# Canvas Dashboard
服务地址：`{base_url}`；请求头：`Authorization: Bearer <CANVAS_DASHBOARD_TOKEN>`。

## 写入规则
{WRITING_RULES}
"""

    if api_file.exists():
        api_client_code = api_file.read_text(encoding="utf-8")
    else:
        api_client_code = "# Canvas Dashboard Python Client\n"

    if readme_file.exists():
        readme_content = readme_file.read_text(encoding="utf-8").replace("{{ base_url }}", base_url)
    else:
        readme_content = "# Canvas Dashboard Agent Skill\n\n参照 SKILL.md 配置地址与 Token。\n\n" + WRITING_RULES

    install_sh = SKILL_DIR / "install.sh"
    install_ps1 = SKILL_DIR / "install.ps1"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_content)
        zf.writestr("canvas_api.py", api_client_code)
        zf.writestr("README.md", readme_content)
        if install_sh.exists():
            zf.writestr("install.sh", install_sh.read_text(encoding="utf-8"))
        if install_ps1.exists():
            zf.writestr("install.ps1", install_ps1.read_text(encoding="utf-8"))
    buf.seek(0)
    response = app.response_class(buf.getvalue(), mimetype="application/zip")
    response.headers["Content-Disposition"] = "attachment; filename=canvas-dashboard-skill.zip"
    return response


# ---- External Agent REST API (Bearer Token Auth) ----


# ---- Agent API for Recurring Todos ----


app.register_blueprint(planning_bp)
app.register_blueprint(agent_bp)


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  Canvas Dashboard")
    print(f"  浏览器打开 → http://{settings.APP_HOST}:{settings.APP_PORT}\n")
    app.run(host=settings.APP_HOST, port=settings.APP_PORT, debug=False)
