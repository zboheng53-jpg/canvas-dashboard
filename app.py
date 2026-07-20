"""Canvas Dashboard - Flask backend for Tongji University students."""
import hmac
import threading
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, render_template, request, session, redirect

import auth
import apple_calendar
import settings
from platform_state import build_platform_todos_response
from storage import JsonFileCorruptionError, locked_json_update, read_json_file, write_json_file
from user_paths import user_dir
from canvas_auth import fetch_canvas_planner, has_feed_url, save_feed_url, load_state, update_state, save_state
from haoke_client import (
    fetch_haoke_todos, has_credentials as has_haoke_credentials,
    save_credentials as save_haoke_credentials,
    load_state as load_haoke_state, update_state as update_haoke_state,
    save_state as save_haoke_state,
    get_cached_todos as get_haoke_cached_todos,
    start_background_refresh as start_haoke_background_refresh,
)
from zhixuemeng_client import (
    send_sms, phone_login, password_login, has_token as has_zxm_token,
    fetch_assignments as fetch_zxm_assignments, fetch_courses as fetch_zxm_courses,
    load_state as load_zxm_state, update_state as update_zxm_state,
    save_state as save_zxm_state,
    save_selected_course, get_selected_course, logout as zxm_logout,
)
import zhihuishu_store
import zhihuishu_login_sessions
import zhihuishu_worker
import schedule_store
import tongji_timetable
import project_store
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("app")

app = Flask(__name__)
app.json.ensure_ascii = False
app.secret_key = auth.get_secret_key()
app.permanent_session_lifetime = auth.SESSION_LIFETIME
app.config["MAX_CONTENT_LENGTH"] = settings.MAX_CONTENT_LENGTH_BYTES
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=settings.COOKIE_SECURE,
)

DATA_DIR = Path(__file__).parent / "data"
CST = timezone(timedelta(hours=8))

# Routes reachable without being logged in.
_LOGIN_EXEMPT_ENDPOINTS = {
    "site_login_page",
    "site_register_page",
    "api_auth_register",
    "api_auth_login",
    "calendar_subscription",
    "healthz",
    "static",
}
_CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CSRF_HEADER = "X-CSRF-Token"
_CSRF_SESSION_KEY = "_csrf_token"

LOGIN_RATE_LIMIT_ATTEMPTS = 8
LOGIN_RATE_LIMIT_SECONDS = 5 * 60
REGISTER_RATE_LIMIT_ATTEMPTS = 5
REGISTER_RATE_LIMIT_SECONDS = 30 * 60
SMS_RATE_LIMIT_ATTEMPTS = 3
SMS_RATE_LIMIT_SECONDS = 10 * 60
_rate_limit_buckets = {}
_rate_limit_lock = threading.Lock()


def _check_data_writable():
    probe = None
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / f".healthz-{secrets.token_hex(8)}.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True}
    except Exception as exc:
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except Exception:
                pass
        return {"ok": False, "error": type(exc).__name__}


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
    result["ok"] = result["error_count"] == 0 and result["unreadable_count"] == 0
    return result


@app.route("/healthz")
def healthz():
    checks = {
        "app": {"ok": True},
        "data_writable": _check_data_writable(),
        "zhihuishu_worker": _check_zhihuishu_worker(),
    }
    ok = all(check.get("ok") is True for check in checks.values())
    return jsonify({"ok": ok, "checks": checks}), 200 if ok else 503


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
        timestamps = [ts for ts in _rate_limit_buckets.get(key, []) if ts > cutoff]
        if len(timestamps) >= attempts:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
            _rate_limit_buckets[key] = timestamps
            return False, retry_after
        timestamps.append(now)
        _rate_limit_buckets[key] = timestamps
    return True, None


def _rate_limited_response(retry_after):
    resp = jsonify({"ok": False, "error": "Too many attempts; try again later."})
    resp.status_code = 429
    resp.headers["Retry-After"] = str(retry_after)
    return resp


def read_json_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def invalid_request_response():
    return jsonify({"ok": False, "error": "鏃犳晥璇锋眰"}), 400


def api_error(code, message, status=400, **extra):
    payload = {"ok": False, "code": code, "error": message}
    payload.update(extra)
    return jsonify(payload), status


def _with_default_error_code(result, code):
    if result.get("ok") is False and "code" not in result:
        result = dict(result)
        result["code"] = code
    return result


def _haoke_default_error_code(result):
    if result.get("need_setup"):
        return "haoke_credentials_missing"
    return "haoke_fetch_failed"


@app.before_request
def _require_login():
    if request.endpoint in _LOGIN_EXEMPT_ENDPOINTS or request.endpoint is None:
        return
    if not session.get("username"):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return redirect("/login")


@app.errorhandler(JsonFileCorruptionError)
def handle_json_file_corruption(error):
    logger.error("Stored JSON is corrupt: %s", error)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "stored data is temporarily unavailable"}), 503
    return "Stored data is temporarily unavailable.", 503


@app.before_request
def _protect_csrf():
    if request.method not in _CSRF_METHODS:
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
    96: ("\u96f7\u66b4\u4f34\u51b0\u96f9", "\u26c8\ufe0f"),
    99: ("\u96f7\u66b4\u4f34\u51b0\u96f9", "\u26c8\ufe0f"),
}
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=31.23&longitude=121.47"
    "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
    "&timezone=Asia/Shanghai"
)


def _todos_file(username):
    return user_dir(username) / "custom_todos.json"


def _todo_timestamp():
    return datetime.now(CST).isoformat()


def _normalize_todos(todos):
    for todo in todos:
        if "labels" not in todo:
            todo["labels"] = []
        if "subtasks" not in todo:
            todo["subtasks"] = []
        if "updated_at" not in todo:
            todo["updated_at"] = todo.get("created_at") or _todo_timestamp()
    return todos


def _load_todos(username):
    return _normalize_todos(read_json_file(_todos_file(username), []))


def _save_todos(username, todos):
    write_json_file(_todos_file(username), todos)


def _remove_expired_completed_todos(username, today):
    def remove_expired(todos):
        remaining = []
        for todo in _normalize_todos(todos):
            if todo.get("done") and todo.get("due_date"):
                try:
                    due_date = datetime.fromisoformat(todo["due_date"]).date()
                except (ValueError, TypeError):
                    remaining.append(todo)
                    continue
                if due_date < today:
                    continue
            remaining.append(todo)
        return remaining

    return locked_json_update(_todos_file(username), [], remove_expired)


def _parse_calendar_due(value):
    try:
        due_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=CST)
    return due_at.astimezone(CST)


def _calendar_items(username):
    now = datetime.now(CST)
    items = []

    for todo in _load_todos(username):
        if todo.get("done"):
            continue
        if todo.get("due_date"):
            items.append({
                "source": "Custom",
                "id": todo.get("id"),
                "title": todo.get("text"),
                "due_date": todo.get("due_date"),
            })
        for index, subtask in enumerate(todo.get("subtasks") or [], start=1):
            if not isinstance(subtask, dict) or subtask.get("done") or not subtask.get("due_date"):
                continue
            subtask_id = subtask.get("id")
            if subtask_id is None:
                subtask_id = index
            items.append({
                "source": "Custom",
                "id": f"{todo.get('id')}-subtask-{subtask_id}",
                "title": subtask.get("text"),
                "due_date": subtask.get("due_date"),
                "course": todo.get("text"),
            })

    def add_cached(source, cached_items, state):
        hidden = set(state.get("hidden", []))
        deleted = set(state.get("deleted", []))
        for item in cached_items:
            item_id = item.get("id")
            due_at = _parse_calendar_due(item.get("due_ts"))
            if item_id in hidden or item_id in deleted or due_at is None or due_at < now:
                continue
            items.append({
                "source": source,
                "id": item_id,
                "title": item.get("title"),
                "due_ts": item.get("due_ts"),
                "course": item.get("course"),
                "url": item.get("url"),
            })

    add_cached("Canvas", read_json_file(user_dir(username) / "canvas_cache.json", []), load_state(username))
    add_cached("Haoke", read_json_file(user_dir(username) / "haoke_cache.json", []), load_haoke_state(username))
    zxm_cache = read_json_file(user_dir(username) / "zhixuemeng_cache.json", {})
    add_cached("Zhixuemeng", zxm_cache.get("items", []) if isinstance(zxm_cache, dict) else [], load_zxm_state(username))
    zhs_cache = zhihuishu_store.load_cache(username)
    add_cached("Zhihuishu", zhs_cache["items"], zhihuishu_store.load_state(username))
    return items


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


@app.route("/login/<platform>")
def login_page(platform):
    if platform not in ("canvas", "haoke", "zhixuemeng", "zhihuishu"):
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
    return jsonify({"ok": True, "path": f"/calendar/{token}.ics"})


@app.route("/calendar/<token>.ics")
def calendar_subscription(token):
    if not settings.APPLE_CALENDAR_ENABLED:
        abort(404)
    username = apple_calendar.username_for_token(token)
    if not username:
        return "Not Found", 404
    response = app.response_class(
        apple_calendar.build_calendar(username, _calendar_items(username), datetime.now(CST)),
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
    return render_template("auth_register.html", icp_number=settings.ICP_NUMBER)


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    allowed, retry_after = _check_rate_limit(
        "auth-register", username, REGISTER_RATE_LIMIT_ATTEMPTS, REGISTER_RATE_LIMIT_SECONDS
    )
    if not allowed:
        return _rate_limited_response(retry_after)
    ok, error = auth.register(username, password)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    session["username"] = username
    session.permanent = True
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
    if not auth.verify_login(username, password):
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    session["username"] = username
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})


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


@app.route("/api/weather")
def api_weather():
    try:
        resp = requests.get(WEATHER_URL, timeout=10)
        data = resp.json()
        current = data.get("current", {})
        code = current.get("weather_code", -1)
        desc, emoji = WMO_CODES.get(code, (f"\u672a\u77e5({code})", "?"))
        return jsonify({
            "ok": True,
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": code,
            "weather_desc": desc,
            "weather_emoji": emoji,
        })
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return jsonify({"ok": False, "error": "weather fetch failed"})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        url = (data.get("calendar_feed_url") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "URL 涓嶈兘涓虹┖"}), 400
        ok, error = save_feed_url(username, url)
        if not ok:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": True})

    return jsonify({"ok": True, "has_feed": has_feed_url(username)})


@app.route("/api/canvas/todos")
def api_canvas_todos():
    username = session["username"]
    result = fetch_canvas_planner(username)
    state = load_state(username)
    result = build_platform_todos_response(
        result,
        state,
        save_state=lambda changed_state: save_state(username, changed_state),
        now=datetime.now(CST),
    )
    return jsonify(result)


@app.route("/api/canvas/state", methods=["GET", "POST"])
def api_canvas_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete") or not item_id:
            return jsonify({"ok": False, "error": "鏃犳晥鎿嶄綔"}), 400
        state = update_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_state(username)})


# ---- Haoke Platform ----


@app.route("/api/haoke/config", methods=["GET", "POST"])
def api_haoke_config():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        haoke_username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        if not haoke_username or not password:
            return api_error("haoke_credentials_required", "username and password required")
        save_haoke_credentials(username, haoke_username, password)
        return jsonify({"ok": True})

    return jsonify({"ok": True, "has_credentials": has_haoke_credentials(username)})


@app.route("/api/haoke/todos")
def api_haoke_todos():
    username = session["username"]
    result = None
    if has_haoke_credentials(username):
        result = get_haoke_cached_todos(username)
        if result is not None:
            result = dict(result)
            is_stale = bool(result.get("stale"))
            if is_stale:
                start_haoke_background_refresh(username)
            result["refreshing"] = is_stale
    if result is None:
        result = fetch_haoke_todos(username)
        result = dict(result)
        result.setdefault("refreshing", False)
    result = _with_default_error_code(result, _haoke_default_error_code(result))
    state = load_haoke_state(username)
    result = build_platform_todos_response(
        result,
        state,
        save_state=lambda changed_state: save_haoke_state(username, changed_state),
        now=datetime.now(CST),
    )
    return jsonify(result)


@app.route("/api/haoke/state", methods=["GET", "POST"])
def api_haoke_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete") or not item_id:
            return jsonify({"ok": False, "error": "鏃犳晥鎿嶄綔"}), 400
        state = update_haoke_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_haoke_state(username)})


# ---- Zhixuemeng Platform ----


@app.route("/api/zhixuemeng/send-sms", methods=["POST"])
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
    return jsonify(result)


@app.route("/api/zhixuemeng/login-password", methods=["POST"])
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
    return jsonify(result)


@app.route("/api/zhixuemeng/logout", methods=["POST"])
def api_zxm_logout():
    zxm_logout(session["username"])
    return jsonify({"ok": True})


@app.route("/api/zhixuemeng/config")
def api_zxm_config():
    username = session["username"]
    has_token = has_zxm_token(username)
    result = {"ok": True, "has_token": has_token}
    if has_token:
        courses_result = fetch_zxm_courses(username)
        if courses_result.get("ok"):
            result["courses"] = courses_result["courses"]
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
    result = fetch_zxm_assignments(username, course_code)
    state = load_zxm_state(username)
    result = build_platform_todos_response(
        result,
        state,
        items_key="items",
        save_state=lambda changed_state: save_zxm_state(username, changed_state),
        now=datetime.now(CST),
    )
    return jsonify(result)


@app.route("/api/zhixuemeng/state", methods=["GET", "POST"])
def api_zxm_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete") or not item_id:
            return jsonify({"ok": False, "error": "鏃犳晥鎿嶄綔"}), 400
        state = update_zxm_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": load_zxm_state(username)})


# ---- Zhihuishu Platform ----


@app.route("/api/zhihuishu/config")
def api_zhihuishu_config():
    username = session["username"]
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
        return jsonify({
            "ok": False,
            "need_setup": True,
            "status": status,
            "data": [],
            "hidden": state["hidden"],
            "highlighted": state["highlighted"],
            "deleted": state["deleted"],
        })

    result = {
        "ok": True,
        "need_setup": status.get("session") in ("not_logged_in", "need_relogin"),
        "data": cache["items"],
        "stale": cache["stale"],
        "fetched_at": cache["fetched_at"],
        "status": status,
    }
    return jsonify(build_platform_todos_response(result, state, auto_delete_expired_hidden=False))


@app.route("/api/zhihuishu/state", methods=["GET", "POST"])
def api_zhihuishu_state():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "鏃犳晥璇锋眰"}), 400
        action = data.get("action", "")
        item_id = data.get("id")
        if action not in ("hide", "unhide", "highlight", "unhighlight", "delete", "undelete") or not item_id:
            return jsonify({"ok": False, "error": "鏃犳晥鎿嶄綔"}), 400
        state = zhihuishu_store.update_state(username, action, item_id)
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": True, "state": zhihuishu_store.load_state(username)})


@app.route("/api/zhihuishu/login-required", methods=["POST"])
def api_zhihuishu_login_required():
    username = session["username"]
    status = zhihuishu_store.save_status(username, {
        "session": "need_relogin",
        "last_error": "闇€瑕侀噸鏂扮櫥褰曟櫤鎱ф爲",
    })
    return jsonify({"ok": True, "status": status})


@app.route("/api/zhihuishu/login-session", methods=["POST"])
def api_zhihuishu_login_session():
    username = session["username"]
    try:
        login_session = zhihuishu_login_sessions.create_session(username)
    except Exception as e:
        logger.exception("Failed to create Zhihuishu login session")
        return jsonify({"ok": False, "error": f"鍚姩鐧诲綍绐楀彛澶辫触: {e}"}), 500
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


@app.route("/api/custom/todos", methods=["GET", "POST"])
def api_custom_todos():
    username = session["username"]
    if request.method == "POST":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "鍐呭涓嶈兘涓虹┖"}), 400
        due_date = (data.get("due_date") or "").strip() or None
        todos = _load_todos(username)
        new_id = max((t["id"] for t in todos), default=0) + 1
        now = _todo_timestamp()
        labels = data.get("labels", [])  # 鏂板鏍囩瀛楁
        todos.append({
            "id": new_id,
            "text": text,
            "done": False,
            "created_at": now,
            "updated_at": now,
            "due_date": due_date,
            "highlighted": False,
            "labels": labels,
            "subtasks": [],
        })
        new_todo = todos[-1]

        def add_todo(current):
            current = _normalize_todos(current)
            new_todo["id"] = max((t["id"] for t in current), default=0) + 1
            current.append(new_todo)
            return current

        locked_json_update(_todos_file(username), [], add_todo)
        return jsonify({"ok": True, "todo": todos[-1]})

    today = datetime.now(CST).date()
    todos = _remove_expired_completed_todos(username, today)

    todos.sort(key=lambda t: (
        1 if t["done"] else 0,
        0 if t.get("due_date") else 1,
        t.get("due_date") or "9999-99-99",
    ))
    return jsonify({"ok": True, "data": todos, "today": datetime.now(CST).strftime("%Y-%m-%d")})


@app.route("/api/custom/todos/<int:todo_id>", methods=["PUT", "DELETE"])
def api_custom_todo_item(todo_id):
    username = session["username"]
    if request.method == "DELETE":
        locked_json_update(
            _todos_file(username),
            [],
            lambda todos: [t for t in _normalize_todos(todos) if t["id"] != todo_id],
        )
        return jsonify({"ok": True})

    if request.method == "PUT":
        data = read_json_request()
        if data is None:
            return invalid_request_response()
        result = {"conflict": False, "todo": None}

        def update_todos(current):
            current = _normalize_todos(current)
            for t in current:
                if t["id"] == todo_id:
                    if (
                        "subtasks" in data
                        and data.get("updated_at")
                        and data.get("updated_at") != t.get("updated_at")
                    ):
                        result["conflict"] = True
                        result["todo"] = dict(t)
                        break
                    if "done" in data:
                        t["done"] = data["done"]
                    if "text" in data:
                        t["text"] = data["text"]
                    if "due_date" in data:
                        t["due_date"] = (data["due_date"] or "").strip() or None
                    if "highlighted" in data:
                        t["highlighted"] = data["highlighted"]
                    if "labels" in data:
                        t["labels"] = data["labels"]
                    if "subtasks" in data:
                        t["subtasks"] = data["subtasks"]
                    t["updated_at"] = _todo_timestamp()
                    result["todo"] = dict(t)
                    break
            return current

        locked_json_update(_todos_file(username), [], update_todos)
        if result["conflict"]:
            return jsonify({
                "ok": False,
                "code": "custom_todo_conflict",
                "error": "Todo changed; refresh and try again",
                "todo": result["todo"],
            }), 409
        return jsonify({"ok": True, "todo": result["todo"]})

    return jsonify({"ok": False, "error": "Method not allowed"}), 405


# ---- Course timetable and simple schedule items ----

def _schedule_item_payload(data, kind):
    if data is None:
        return None
    title = (data.get("title") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    end_time = (data.get("end_time") or "").strip()
    if not title or not re.fullmatch(r"\d{2}:\d{2}", start_time) or not re.fullmatch(r"\d{2}:\d{2}", end_time) or start_time >= end_time:
        return None
    payload = {"title": title, "start_time": start_time, "end_time": end_time}
    if kind == "recurring":
        weekday = data.get("weekday")
        if not isinstance(weekday, int) or not 0 <= weekday <= 6:
            return None
        payload.update({"weekday": weekday, "enabled": bool(data.get("enabled", True))})
        if "skipped_dates" in data:
            payload["skipped_dates"] = [value for value in data["skipped_dates"] if isinstance(value, str)]
    else:
        try:
            payload["date"] = date.fromisoformat((data.get("date") or "").strip()).isoformat()
        except ValueError:
            return None
    return payload


def _schedule_overlap(username, kind, payload, ignore_id=None):
    items = schedule_store.load_items(username)
    weekday = payload.get("weekday") if kind == "recurring" else date.fromisoformat(payload["date"]).weekday()
    candidate_date = date.fromisoformat(payload["date"]) if kind == "one_off" else None
    courses = schedule_store.load_courses(username)
    for course in courses.get("courses", []):
        for meeting in course.get("sessions", []):
            if candidate_date is None:
                same_day = meeting.get("weekday") == weekday
            elif meeting.get("date_start") and meeting.get("date_end"):
                same_day = meeting["date_start"] <= candidate_date.isoformat() <= meeting["date_end"]
            else:
                same_day = meeting.get("weekday") == weekday
            if same_day and payload["start_time"] < meeting.get("end_time", "") and meeting.get("start_time", "") < payload["end_time"]:
                return True
    for item in items.get("recurring", []):
        if kind == "recurring" and item.get("id") == ignore_id:
            continue
        if item.get("enabled", True) and item.get("weekday") == weekday and payload["start_time"] < item.get("end_time", "") and item.get("start_time", "") < payload["end_time"]:
            return True
    for item in items.get("one_off", []):
        if kind == "one_off" and item.get("id") == ignore_id:
            continue
        if kind == "one_off":
            same_day = item.get("date") == payload.get("date")
        else:
            same_day = date.fromisoformat(item.get("date")).weekday() == weekday if item.get("date") else False
        if same_day and payload["start_time"] < item.get("end_time", "") and item.get("start_time", "") < payload["end_time"]:
            return True
    return False


@app.route("/api/schedule", methods=["GET"])
def api_schedule():
    username = session["username"]
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username), "items": schedule_store.load_items(username)})


@app.route("/api/schedule/refresh", methods=["POST"])
def api_schedule_refresh():
    username = session["username"]
    data = read_json_request()
    if data is None:
        return invalid_request_response()
    tongji_username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not tongji_username or not password:
        return api_error("timetable_credentials_required", "请输入统一身份认证账号和密码")
    try:
        courses = tongji_timetable.fetch_selected_courses_with_credentials(tongji_username, password)
    except tongji_timetable.TimetableLoginError as exc:
        return api_error("timetable_login_failed", str(exc), 401)
    except tongji_timetable.TimetableFetchError as exc:
        return api_error("timetable_fetch_failed", str(exc), 502)
    term, _, semester_start = get_term_info()
    schedule_store.save_courses(username, term, semester_start, courses, datetime.now(CST).isoformat())
    return jsonify({"ok": True, "courses": schedule_store.load_courses(username)})


@app.route("/api/schedule/<kind>", methods=["POST"])
def api_schedule_item_create(kind):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    username = session["username"]
    payload = _schedule_item_payload(read_json_request(), "recurring" if kind == "recurring" else "one_off")
    if payload is None:
        return invalid_request_response()
    item = schedule_store.create_item(username, "recurring" if kind == "recurring" else "one_off", payload)
    return jsonify({"ok": True, "item": item, "overlap": _schedule_overlap(username, "recurring" if kind == "recurring" else "one_off", payload, item["id"])})


@app.route("/api/schedule/<kind>/<int:item_id>", methods=["PUT", "DELETE"])
def api_schedule_item(kind, item_id):
    if kind not in {"recurring", "one-off"}:
        abort(404)
    username = session["username"]
    normalized_kind = "recurring" if kind == "recurring" else "one_off"
    if request.method == "DELETE":
        return jsonify({"ok": schedule_store.delete_item(username, normalized_kind, item_id)})
    payload = _schedule_item_payload(read_json_request(), normalized_kind)
    if payload is None:
        return invalid_request_response()
    item = schedule_store.update_item(username, normalized_kind, item_id, payload)
    if item is None:
        return api_error("schedule_item_not_found", "日程不存在", 404)
    return jsonify({"ok": True, "item": item, "overlap": _schedule_overlap(username, normalized_kind, payload, item_id)})


@app.route("/api/schedule/today")
def api_schedule_today():
    username = session["username"]
    today = datetime.now(CST).date()
    _, _, semester_start = get_term_info()
    result = schedule_store.today_entries(username, today, semester_start)
    for item in _calendar_items(username):
        due_date = item.get("due_date")
        due_at = _parse_calendar_due(item.get("due_ts")) if item.get("due_ts") else None
        if due_date == today.isoformat() or (due_at and due_at.date() == today):
            course_name = item.get("course") or ""
            if due_at and due_at.strftime("%H:%M") != "00:00":
                timed_entry = {
                    "kind": "deadline",
                    "title": item.get("title") or "Deadline",
                    "location": course_name,
                    "start_time": due_at.strftime("%H:%M"),
                    "end_time": due_at.strftime("%H:%M")
                }
                if course_name:
                    timed_entry["course"] = course_name
                result["timed"].append(timed_entry)
            else:
                deadline_entry = {"title": item.get("title") or "Deadline"}
                if course_name:
                    deadline_entry["course"] = course_name
                result["deadlines"].append(deadline_entry)
    result["timed"].sort(key=lambda item: (item["start_time"], item["title"]))
    return jsonify({"ok": True, "date": today.isoformat(), **result})


# ---- Long-term projects ----

def _project_payload(data, partial=False):
    if data is None:
        return None
    payload = {}
    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 100: return None
        payload["name"] = name
    if "progress" in data:
        progress = data["progress"]
        if not isinstance(progress, int) or isinstance(progress, bool) or not 0 <= progress <= 100: return None
        payload["progress"] = progress
    if "due_date" in data:
        raw = (data.get("due_date") or "").strip()
        try: payload["due_date"] = date.fromisoformat(raw).isoformat() if raw else None
        except ValueError: return None
    if "next_action" in data:
        action = (data.get("next_action") or "").strip()
        if len(action) > 200: return None
        payload["next_action"] = action
    return payload


@app.route("/api/projects", methods=["GET", "POST"])
def api_projects():
    username = session["username"]
    if request.method == "POST":
        payload = _project_payload(read_json_request())
        if payload is None: return invalid_request_response()
        return jsonify({"ok": True, "project": project_store.create_project(username, payload)})
    return jsonify({"ok": True, "projects": project_store.load_projects(username)})


@app.route("/api/projects/overview")
def api_projects_overview():
    active = [project for project in project_store.load_projects(session["username"]) if project.get("status") == "active"]
    return jsonify({"ok": True, "projects": active[:3], "has_more": len(active) > 3})


@app.route("/api/projects/<int:project_id>", methods=["PUT"])
def api_project(project_id):
    payload = _project_payload(read_json_request(), partial=True)
    if payload is None or not payload: return invalid_request_response()
    project = project_store.update_project(session["username"], project_id, payload)
    if project is None: return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "project": project})


@app.route("/api/projects/<int:project_id>/archive", methods=["POST"])
def api_project_archive(project_id):
    project = project_store.update_project(session["username"], project_id, {"status": "archived"})
    if project is None: return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "project": project})


@app.route("/api/projects/<int:project_id>/goals", methods=["POST"])
def api_project_goal_create(project_id):
    data = read_json_request(); text = (data.get("text") or "").strip() if data else ""
    if not text or len(text) > 160: return invalid_request_response()
    goal = project_store.create_goal(session["username"], project_id, text)
    if goal is None: return api_error("project_not_found", "项目不存在", 404)
    return jsonify({"ok": True, "goal": goal})


@app.route("/api/projects/<int:project_id>/goals/<int:goal_id>", methods=["PUT", "DELETE"])
def api_project_goal(project_id, goal_id):
    if request.method == "DELETE":
        return jsonify({"ok": project_store.delete_goal(session["username"], project_id, goal_id)})
    data = read_json_request()
    if not data or ("text" not in data and "done" not in data): return invalid_request_response()
    changes = {}
    if "text" in data:
        text = (data.get("text") or "").strip()
        if not text or len(text) > 160: return invalid_request_response()
        changes["text"] = text
    if "done" in data:
        if not isinstance(data["done"], bool): return invalid_request_response()
        changes["done"] = data["done"]
    goal = project_store.update_goal(session["username"], project_id, goal_id, changes)
    if goal is None: return api_error("goal_not_found", "目标不存在", 404)
    return jsonify({"ok": True, "goal": goal})


@app.route("/api/projects/<int:project_id>/goals/reorder", methods=["POST"])
def api_project_goal_reorder(project_id):
    data = read_json_request(); goal_ids = data.get("goal_ids") if data else None
    if not isinstance(goal_ids, list) or not all(isinstance(value, int) for value in goal_ids): return invalid_request_response()
    goals = project_store.reorder_goals(session["username"], project_id, goal_ids)
    if goals is None: return api_error("goal_order_invalid", "目标顺序无效", 400)
    return jsonify({"ok": True, "goals": goals})


# ---- School Term / Week ----

TERM_START = datetime.combine(settings.TERM_START_DATE, datetime.min.time(), tzinfo=CST)
TERM_LABEL = settings.TERM_LABEL

_TERM_CONFIG_FILE = DATA_DIR / "term_config.json"


def _compute_week_num(target_date, semester_start_date):
    """Compute current week number given a semester start date.
    Week 1 starts on the Monday containing or following the semester start date.
    """
    days_until_monday = (7 - semester_start_date.weekday()) % 7
    start_monday = semester_start_date + timedelta(days=days_until_monday)
    days_from_start_monday = (target_date - start_monday).days
    return days_from_start_monday // 7 + 1


def _load_term_config(target_date=None):
    """Load term config and compute (term_label, week_num, semester_start_str) for target_date."""
    if target_date is None:
        target_date = datetime.now(CST).date()

    data = read_json_file(_TERM_CONFIG_FILE, {})
    semesters = data.get("semesters")

    if isinstance(semesters, list) and len(semesters) > 0:
        parsed_semesters = []
        for s in semesters:
            if not isinstance(s, dict):
                continue
            raw_start = s.get("start_date") or s.get("term_start")
            label = s.get("term_label") or s.get("term")
            weeks = s.get("weeks", 20)
            if raw_start and label:
                try:
                    dt_start = date.fromisoformat(raw_start)
                    days_until_monday = (7 - dt_start.weekday()) % 7
                    start_monday = dt_start + timedelta(days=days_until_monday)
                    parsed_semesters.append({
                        "label": label,
                        "start_monday": start_monday,
                        "weeks": weeks,
                    })
                except (TypeError, ValueError):
                    pass

        if parsed_semesters:
            parsed_semesters.sort(key=lambda item: item["start_monday"])
            
            # Check if target_date falls within any configured semester
            for i, sem in enumerate(parsed_semesters):
                end_sunday = sem["start_monday"] + timedelta(weeks=sem["weeks"]) - timedelta(days=1)
                if sem["start_monday"] <= target_date <= end_sunday:
                    week_num = (target_date - sem["start_monday"]).days // 7 + 1
                    return sem["label"], week_num, sem["start_monday"].strftime("%Y-%m-%d")

            # If before first configured semester
            if target_date < parsed_semesters[0]["start_monday"]:
                first = parsed_semesters[0]
                week_num = _compute_week_num(target_date, first["start_monday"])
                return first["label"], week_num, first["start_monday"].strftime("%Y-%m-%d")

            # Check if in gap between semesters or after last semester
            for i in range(len(parsed_semesters) - 1):
                prev_sem = parsed_semesters[i]
                next_sem = parsed_semesters[i + 1]
                prev_end = prev_sem["start_monday"] + timedelta(weeks=prev_sem["weeks"]) - timedelta(days=1)
                if prev_end < target_date < next_sem["start_monday"]:
                    week_num = (target_date - prev_sem["start_monday"]).days // 7 + 1
                    return prev_sem["label"], week_num, prev_sem["start_monday"].strftime("%Y-%m-%d")

            # If after last semester
            last = parsed_semesters[-1]
            week_num = (target_date - last["start_monday"]).days // 7 + 1
            return last["label"], week_num, last["start_monday"].strftime("%Y-%m-%d")

    # Fallback to single term_config or settings default
    label = data.get("term_label") or data.get("term") or TERM_LABEL
    start_raw = data.get("term_start") or data.get("semester_start")
    if start_raw:
        try:
            start_date = date.fromisoformat(start_raw)
            return label, _compute_week_num(target_date, start_date), start_date.strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            logger.warning("Invalid term config start date: %r", start_raw)

    return TERM_LABEL, _compute_week_num(target_date, TERM_START.date()), TERM_START.date().strftime("%Y-%m-%d")


def get_term_info(now=None):
    """Return (term_label, week_num, semester_start_str).
    Uses offline calendar configuration to compute active term and week number.
    """
    if now is None:
        now = datetime.now(CST)
    return _load_term_config(now.date())


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

_HOLIDAY_CACHE_FILE = DATA_DIR / "holiday_cache.json"
_HOLIDAY_CACHE_TTL = settings.HOLIDAY_CACHE_TTL_SECONDS
_HOLIDAY_FETCH_RETRY_INTERVAL = settings.HOLIDAY_FETCH_RETRY_INTERVAL_SECONDS
_holiday_fetch_lock = threading.Lock()
_holiday_fetch_failed_at = None


def _load_holiday_cache():
    """Load holiday data from disk cache. Returns list of holiday dicts or None."""
    if _HOLIDAY_CACHE_FILE.exists():
        try:
            data = json.loads(_HOLIDAY_CACHE_FILE.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            age = (datetime.now(CST) - fetched_at).total_seconds()
            if age < _HOLIDAY_CACHE_TTL:
                return data.get("holidays")
        except Exception:
            pass
    return None


def _save_holiday_cache(holidays):
    """Save holiday data to disk cache."""
    _HOLIDAY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(_HOLIDAY_CACHE_FILE, {
        "holidays": holidays,
        "fetched_at": datetime.now(CST).isoformat(),
    })


def _fetch_holidays():
    """Fetch holiday data for current year from 1.tongji.edu.cn workbench API via CDP proxy.
    Returns list of dicts with keys: name, begin_day, end_day (as datetime.date).
    """
    try:
        year = datetime.now(CST).year
        # Open a tab on workbench to get authenticated session
        r = requests.get(
            f"{settings.CDP_PROXY_BASE_URL}/new",
            params={"url": "https://1.tongji.edu.cn/workbench"},
            timeout=15,
        )
        target_id = r.json()["targetId"]

        import time
        time.sleep(2)

        # Call the holiday API endpoint via the browser (uses auth cookies)
        r = requests.post(
            f"{settings.CDP_PROXY_BASE_URL}/eval",
            params={"target": target_id},
            data=(
                "new Promise(function(resolve){"
                "var x=new XMLHttpRequest();"
                "x.open('GET','/api/baseresservice/holiday/queryHolidayByYear?year=" + str(year) + "');"
                "x.onload=function(){resolve(x.responseText)};"
                "x.onerror=function(){resolve('XHR error')};"
                "x.send()"
                "})"
            ),
            timeout=15,
        )
        resp_text = r.json()["value"]
        api_resp = json.loads(resp_text)

        # Close tab
        requests.get(
            f"{settings.CDP_PROXY_BASE_URL}/close",
            params={"target": target_id},
            timeout=5,
        )

        if api_resp.get("code") != 200:
            logger.warning(f"Holiday API returned error: {api_resp}")
            return None

        holidays = []
        for h in api_resp.get("data", []):
            begin_dt = datetime.fromtimestamp(h["beginDay"] / 1000, tz=CST)
            end_dt = datetime.fromtimestamp(h["endDay"] / 1000, tz=CST)
            holidays.append({
                "name": h.get("remark", h.get("holidayName", "")),
                "begin_day": begin_dt.date().isoformat(),
                "end_day": end_dt.date().isoformat(),
            })
        return holidays
    except Exception as e:
        logger.warning(f"Holiday fetch via CDP failed: {e}")
    return None


def _get_holidays():
    """Get holiday list with cache. Returns list or empty list."""
    global _holiday_fetch_failed_at

    cached = _load_holiday_cache()
    if cached is not None:
        return cached

    now = datetime.now(CST)
    if (_holiday_fetch_failed_at and
            (now - _holiday_fetch_failed_at).total_seconds() < _HOLIDAY_FETCH_RETRY_INTERVAL):
        return []

    if not _holiday_fetch_lock.acquire(blocking=False):
        return []

    try:
        cached = _load_holiday_cache()
        if cached is not None:
            return cached

        fresh = _fetch_holidays()
        if fresh is not None:
            _holiday_fetch_failed_at = None
            _save_holiday_cache(fresh)
            return fresh

        _holiday_fetch_failed_at = datetime.now(CST)
        return []
    finally:
        _holiday_fetch_lock.release()


def _check_today_holiday(now):
    """Check if today is a holiday. Returns (is_holiday, holiday_name)."""
    today = now.date()
    holidays = _get_holidays()
    for h in holidays:
        begin = date.fromisoformat(h["begin_day"])
        end = date.fromisoformat(h["end_day"])
        if begin <= today <= end:
            return True, h["name"]
    return False, ""


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  Canvas Dashboard")
    print(f"  娴忚鍣ㄦ墦寮€ 鈫?http://{settings.APP_HOST}:{settings.APP_PORT}\n")
    app.run(host=settings.APP_HOST, port=settings.APP_PORT, debug=False)


