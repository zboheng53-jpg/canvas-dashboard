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
from flask import Flask, jsonify, render_template, request, session, redirect

import auth
import settings
from platform_state import build_platform_todos_response
from storage import locked_json_update, read_json_file, write_json_file
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
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("app")

app = Flask(__name__)
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
_LOGIN_EXEMPT_ENDPOINTS = {"site_login_page", "site_register_page", "api_auth_register", "api_auth_login", "static"}
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
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
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


@app.before_request
def _protect_csrf():
    if request.method not in _CSRF_METHODS:
        return
    expected = session.get(_CSRF_SESSION_KEY)
    supplied = request.headers.get(_CSRF_HEADER, "")
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        return _csrf_failed_response()


WMO_CODES = {
    0: ("Clear", "sun"), 1: ("Mostly clear", "sun"), 2: ("Partly cloudy", "cloud"), 3: ("Cloudy", "cloud"),
    45: ("Fog", "fog"), 48: ("Rime fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Rain showers", "rain"), 81: ("Rain showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm with hail", "storm"), 99: ("Thunderstorm with hail", "storm"),
}
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=31.23&longitude=121.47"
    "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
    "&timezone=Asia/Shanghai"
)


def _load_todos(username):
    todos_file = user_dir(username) / "custom_todos.json"
    if not todos_file.exists():
        return []
    with open(todos_file, "r", encoding="utf-8") as f:
        todos = json.load(f)
        # 纭繚鎵€鏈夊緟鍔炰簨椤归兘鏈夋爣绛惧拰瀛愪换鍔″瓧娈碉紙鍏煎鏃ф暟鎹級
        for todo in todos:
            if "labels" not in todo:
                todo["labels"] = []
            if "subtasks" not in todo:
                todo["subtasks"] = []
        return todos


def _save_todos(username, todos):
    write_json_file(user_dir(username) / "custom_todos.json", todos)


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


@app.route("/")
def index():
    return render_template("index.html", username=session.get("username"))


@app.route("/login/<platform>")
def login_page(platform):
    if platform not in ("canvas", "haoke", "zhixuemeng", "zhihuishu"):
        return "Not Found", 404
    return render_template(f"login_{platform}.html", username=session.get("username"))


# ---- Site-wide account system ----


@app.route("/login")
def site_login_page():
    if session.get("username"):
        return redirect("/")
    return render_template("auth_login.html")


@app.route("/register")
def site_register_page():
    if session.get("username"):
        return redirect("/")
    return render_template("auth_register.html")


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
        return jsonify({"ok": False, "error": "鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒"}), 401
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
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
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
        desc, emoji = WMO_CODES.get(code, (f"Unknown({code})", "?"))
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
        save_feed_url(username, url)
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

    todos = _load_todos(username)

    # Auto-delete: completed items whose due_date has passed (day after due)
    today = datetime.now(CST).date()
    remaining = []
    changed = False
    for t in todos:
        if t.get("done") and t.get("due_date"):
            try:
                due_date = datetime.fromisoformat(t["due_date"]).date()
            except (ValueError, TypeError):
                remaining.append(t)
                continue
            if due_date < today:
                changed = True
                continue  # skip = delete
        remaining.append(t)
    if changed:
        _save_todos(username, remaining)
    todos = remaining

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


# ---- School Term / Week ----

TERM_START = datetime.combine(settings.TERM_START_DATE, datetime.min.time(), tzinfo=CST)
TERM_LABEL = settings.TERM_LABEL

_TERM_CACHE_FILE = DATA_DIR / "term_cache.json"
_TERM_CONFIG_FILE = DATA_DIR / "term_config.json"


def _load_term_config():
    data = read_json_file(_TERM_CONFIG_FILE, {})
    label = data.get("term_label") or data.get("term") or TERM_LABEL
    start_raw = data.get("term_start") or data.get("semester_start")
    if start_raw:
        try:
            return label, date.fromisoformat(start_raw)
        except (TypeError, ValueError):
            logger.warning("Invalid term config start date: %r", start_raw)
    return TERM_LABEL, TERM_START.date()


def _load_term_cache():
    if _TERM_CACHE_FILE.exists():
        try:
            data = json.loads(_TERM_CACHE_FILE.read_text(encoding="utf-8"))
            return {"data": data.get("data"), "fetched_at": datetime.fromisoformat(data["fetched_at"])}
        except Exception:
            pass
    return {"data": None, "fetched_at": None}


def _save_term_cache(cache):
    _TERM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(_TERM_CACHE_FILE, {
        "data": cache["data"],
        "fetched_at": cache["fetched_at"].isoformat() if cache["fetched_at"] else None,
    })


_scraped_term_cache = _load_term_cache()


def _scrape_term_from_tongji():
    """Get current semester and week from the Tongji calendar page via CDP."""
    try:
        r = requests.get(
            f"{settings.CDP_PROXY_BASE_URL}/new",
            params={"url": "https://1.tongji.edu.cn/schoolCalendars"},
            timeout=15,
        )
        target_id = r.json()["targetId"]

        import time
        time.sleep(3)

        r = requests.post(
            f"{settings.CDP_PROXY_BASE_URL}/eval",
            params={"target": target_id},
            data="Array.from(document.querySelectorAll('.el-tag--light')).map(t => t.innerText.trim()).join('||')",
            timeout=10,
        )
        text = r.json()["value"]
        parts = [p.strip() for p in text.split("||")]

        requests.get(
            f"{settings.CDP_PROXY_BASE_URL}/close",
            params={"target": target_id},
            timeout=5,
        )

        if len(parts) < 2:
            return None

        semester_raw, week_raw = parts[0], parts[1]
        year_match = re.search(r"(\d{4}-\d{4})", semester_raw)
        sem_digits = re.findall(r"\d+", semester_raw)
        week_match = re.search(r"\d+", week_raw)
        if not year_match or not sem_digits or not week_match:
            return None

        year_range = year_match.group(1)
        sem_num = int(sem_digits[-1])
        week_num = int(week_match.group(0))
        sem_label = f"{year_range} semester {sem_num}"

        today = datetime.now(CST).date()
        current_monday = today - timedelta(days=today.weekday())
        semester_start_monday = current_monday - timedelta(weeks=week_num - 1)

        return {
            "term": sem_label,
            "week": week_num,
            "semester_start": semester_start_monday.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.warning(f"Term scraping via CDP failed: {e}")
    return None

def _compute_week_num(now, semester_start_date):
    """Compute current week number given a semester start date.
    Week 1 starts on the Monday containing or following the semester start date.
    """
    days_until_monday = (7 - semester_start_date.weekday()) % 7
    start_monday = semester_start_date + timedelta(days=days_until_monday)
    days_from_start_monday = (now.date() - start_monday).days
    return days_from_start_monday // 7 + 1


def get_term_info():
    """Return (term_label, week_num, semester_start_str).
    Uses disk-cached CDP data when available (no TTL), falls back to local term config.
    CDP scrape is only triggered manually via POST /api/term/refresh.
    """
    global _scraped_term_cache
    now = datetime.now(CST)

    if _scraped_term_cache["data"] and _scraped_term_cache["fetched_at"]:
        s = _scraped_term_cache["data"]
        start_date = datetime.strptime(s["semester_start"], "%Y-%m-%d").date()
        return s["term"], _compute_week_num(now, start_date), s["semester_start"]

    term_label, start_date = _load_term_config()
    week_num = _compute_week_num(now, start_date)
    return term_label, week_num, start_date.strftime("%Y-%m-%d")


@app.route("/api/term")
def api_term():
    now = datetime.now(CST)
    term_label, week_num, semester_start = get_term_info()

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


@app.route("/api/term/refresh", methods=["POST"])
def api_term_refresh():
    """Manually trigger CDP scrape to update term info."""
    global _scraped_term_cache
    scraped = _scrape_term_from_tongji()
    if scraped:
        _scraped_term_cache["data"] = scraped
        _scraped_term_cache["fetched_at"] = datetime.now(CST)
        _save_term_cache(_scraped_term_cache)
        start_date = datetime.strptime(scraped["semester_start"], "%Y-%m-%d").date()
        return jsonify({
            "ok": True,
            "term": scraped["term"],
            "week": _compute_week_num(datetime.now(CST), start_date),
        })
    return jsonify({"ok": False, "error": "CDP 鎶撳彇澶辫触锛岃纭宸茬櫥褰?1.tongji.edu.cn 涓?CDP proxy 姝ｅ湪杩愯"}), 502


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



