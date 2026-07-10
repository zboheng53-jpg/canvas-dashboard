"""Zhixuemeng (智学盟) client for Tongji University.

Login flow:
  1. POST /sys/sms with {mobile, smsmode: "0"} to send verification code
  2. POST /sys/phoneLogin with {mobile, captcha} to login and get token
  3. Use X-Access-Token header for subsequent API calls
"""
import base64
import json
import logging
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import requests
from cryptography.fernet import Fernet

import settings
from platform_state import PlatformStateStore
from storage import load_or_create_bytes, read_json_file, write_json_file
from user_paths import user_dir, DATA_DIR

logger = logging.getLogger(__name__)

BASE_URL = settings.ZHIXUEMENG_BASE_URL
CST = timezone(timedelta(hours=8))
_state_store = PlatformStateStore(lambda username: user_dir(username) / "zhixuemeng_state.json", str)

KEY_FILE = DATA_DIR / ".encryption_key"

# In-memory token cache, keyed by username
_token_cache: dict[str, dict] = {}


def _get_or_create_key():
    return load_or_create_bytes(KEY_FILE, Fernet.generate_key)


def _encrypt_token(plain: str) -> str:
    f = Fernet(_get_or_create_key())
    return f.encrypt(plain.encode()).decode()


def _decrypt_token(cipher: str) -> str:
    f = Fernet(_get_or_create_key())
    return f.decrypt(cipher.encode()).decode()


# ---- SMS ----

def send_sms(phone: str) -> dict:
    """Send SMS verification code to phone."""
    try:
        r = requests.post(
            f"{BASE_URL}/sys/sms",
            json={"mobile": phone, "smsmode": "0"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("success"):
            return {"ok": True, "message": "验证码已发送"}
        return {"ok": False, "error": data.get("message", "发送失败")}
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return {"ok": False, "error": f"发送失败: {e}"}


# ---- Login ----

def phone_login(username: str, phone: str, captcha: str) -> dict:
    """Login with phone + SMS code."""
    try:
        r = requests.post(
            f"{BASE_URL}/sys/phoneLogin",
            json={"mobile": phone, "captcha": captcha},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("success"):
            token = data["result"]["token"]
            _save_token(username, token)
            _token_cache[username] = {"token": token, "expires_at": datetime.now(CST) + timedelta(hours=2)}
            return {"ok": True}
        return {"ok": False, "error": data.get("message", "登录失败")}
    except Exception as e:
        logger.error(f"Phone login failed: {e}")
        return {"ok": False, "error": f"登录失败: {e}"}


def password_login(username: str, zxm_username: str, password: str) -> dict:
    """Login with username + password (fallback)."""
    try:
        r = requests.post(
            f"{BASE_URL}/sys/mLogin",
            json={"username": zxm_username, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("success"):
            token = data["result"]["token"]
            _save_token(username, token)
            _token_cache[username] = {"token": token, "expires_at": datetime.now(CST) + timedelta(hours=2)}
            return {"ok": True}
        return {"ok": False, "error": data.get("message", "登录失败")}
    except Exception as e:
        logger.error(f"Password login failed: {e}")
        return {"ok": False, "error": f"登录失败: {e}"}


def _save_token(username: str, token: str):
    config_file = user_dir(username) / "config.json"
    config = read_json_file(config_file, {})
    config["zhixuemeng_token_encrypted"] = _encrypt_token(token)
    write_json_file(config_file, config)


def _load_token(username: str) -> str | None:
    config_file = user_dir(username) / "config.json"
    if not config_file.exists():
        return None
    try:
        config = read_json_file(config_file, {})
        enc = config.get("zhixuemeng_token_encrypted")
        if enc:
            return _decrypt_token(enc)
    except Exception:
        pass
    return None


def has_token(username: str) -> bool:
    cache = _token_cache.get(username, {})
    if cache.get("token") and cache.get("expires_at"):
        if datetime.now(CST) < cache["expires_at"]:
            return True
    stored = _load_token(username)
    return stored is not None


def logout(username: str):
    _token_cache.pop(username, None)
    config_file = user_dir(username) / "config.json"
    cache_file = user_dir(username) / "zhixuemeng_cache.json"
    if config_file.exists():
        try:
            config = read_json_file(config_file, {})
            config.pop("zhixuemeng_token_encrypted", None)
            config.pop("zhixuemeng_selected_course", None)
            write_json_file(config_file, config)
        except Exception:
            pass
    try:
        cache_file.unlink(missing_ok=True)
    except Exception:
        pass


def _get_token(username: str) -> str | None:
    cache = _token_cache.get(username, {})
    if cache.get("token") and cache.get("expires_at"):
        if datetime.now(CST) < cache["expires_at"]:
            return cache["token"]
    stored = _load_token(username)
    if stored:
        _token_cache[username] = {"token": stored, "expires_at": datetime.now(CST) + timedelta(hours=2)}
        return stored
    return None


def _get_zxm_username(username: str) -> str | None:
    """Extract zhixuemeng's own username from JWT token payload."""
    token = _get_token(username)
    if not token:
        return None
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("username")
    except Exception:
        return None


# ---- Course / Assignment fetching ----

def fetch_courses(username: str) -> dict:
    """Fetch courses for the current user (filtered by JWT username)."""
    token = _get_token(username)
    if not token:
        return {"ok": False, "error": "未登录"}
    zxm_username = _get_zxm_username(username)
    if not zxm_username:
        return {"ok": False, "error": "无法识别用户"}
    try:
        r = requests.get(
            f"{BASE_URL}/edu/eduCourseUser/list",
            params={"pageSize": "10000", "username": zxm_username},
            headers={"X-Access-Token": token},
            timeout=15,
        )
        data = r.json()
        if data.get("success"):
            records = data["result"]["records"]
            seen = set()
            courses = []
            for rec in records:
                cc = rec.get("courseCode")
                if cc and cc not in seen:
                    seen.add(cc)
                    courses.append({
                        "courseCode": cc,
                        "courseName": rec.get("courseName", ""),
                        "className": rec.get("className", ""),
                        "semester": rec.get("semester_dictText", ""),
                    })
            courses.sort(key=lambda c: c["courseCode"])
            return {"ok": True, "courses": courses}
        return {"ok": False, "error": data.get("message", "获取课程失败")}
    except Exception as e:
        logger.error(f"Fetch courses failed: {e}")
        return {"ok": False, "error": f"获取课程失败: {e}"}


def get_selected_course(username: str) -> str | None:
    """Get the saved selected course code, or auto-detect one with assignments."""
    config_file = user_dir(username) / "config.json"
    if config_file.exists():
        try:
            config = read_json_file(config_file, {})
            return config.get("zhixuemeng_selected_course")
        except Exception:
            pass
    return None


def save_selected_course(username: str, course_code: str):
    config_file = user_dir(username) / "config.json"
    config = read_json_file(config_file, {})
    config["zhixuemeng_selected_course"] = course_code
    write_json_file(config_file, config)


def _parse_assignment(rec, course_code_used):
    """Parse a single assignment record into unified format.
    Returns None if the assignment has a past endTime.
    """
    title = rec.get("title", "未命名作业")
    end_time_str = rec.get("endTime") or ""
    due_str = ""
    due_ts = None

    if end_time_str:
        try:
            dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=CST)
            if dt >= datetime.now(CST):
                due_ts = dt
                due_str = dt.strftime("%m-%d %H:%M")
            else:
                return None
        except ValueError:
            pass

    course_name = rec.get("courseName", "")
    raw_id = rec.get("id", "")

    return {
        "id": f"zxm_{raw_id}",
        "title": title,
        "course": course_name,
        "due_str": due_str,
        "due_ts": due_ts.isoformat() if due_ts else None,
        "type": rec.get("workCls_dictText", "作业"),
        "type_raw": "assignment",
        "url": f"https://h5.zhixuemeng.com/#/pages/class/banji_bjzy?courseCode={course_code_used}",
    }


def _scan_course(token, course_code):
    """Fetch assignments for a single course. Returns list of assignment dicts."""
    try:
        r = requests.get(
            f"{BASE_URL}/edu/eduCourseWork/todoList",
            params={"courseCode": course_code, "workCls": "10", "pageSize": "10000"},
            headers={"X-Access-Token": token},
            timeout=15,
        )
        data = r.json()
        if data.get("success"):
            return [p for p in (_parse_assignment(rec, course_code) for rec in data["result"]["records"]) if p is not None]
    except Exception as e:
        logger.warning(f"Failed to scan course {course_code}: {e}")
    return []


CACHE_TTL = settings.ZHIXUEMENG_CACHE_TTL_SECONDS  # 30 minutes


def fetch_assignments(username: str, course_code: str = None) -> dict:
    """Fetch assignments from zhixuemeng, scanning all enrolled courses.

    Results are cached for 30 minutes. Pass course_code to filter.
    """
    token = _get_token(username)
    if not token:
        return {"ok": False, "error": "未登录，请先登录智学盟", "items": [], "need_setup": True}

    # Check cache
    cached = None
    zxm_username = _get_zxm_username(username)
    if not zxm_username:
        return {"ok": False, "error": "无法识别用户", "items": []}

    cache_file = user_dir(username) / "zhixuemeng_cache.json"
    if cache_file.exists():
        try:
            raw = read_json_file(cache_file, {})
            ts = raw.get("_ts", 0)
            if raw.get("_user") == zxm_username and time_module.time() - ts < CACHE_TTL:
                cached = raw
                logger.info(f"Using cached assignments ({len(raw.get('items', []))} items)")
        except Exception:
            pass

    if cached is not None:
        items = cached.get("items", [])
    else:
        # Get courses for the current user only
        try:
            r = requests.get(
                f"{BASE_URL}/edu/eduCourseUser/list",
                params={"pageSize": "10000", "username": zxm_username},
                headers={"X-Access-Token": token},
                timeout=15,
            )
            data = r.json()
            if not data.get("success"):
                return {"ok": False, "error": "获取课程列表失败", "items": []}

            seen = set()
            course_codes = []
            for rec in data["result"]["records"]:
                cc = rec.get("courseCode")
                if cc and cc not in seen:
                    seen.add(cc)
                    course_codes.append(cc)
        except Exception as e:
            logger.error(f"Failed to fetch course list: {e}")
            return {"ok": False, "error": f"获取课程列表失败: {e}", "items": []}

        logger.info(f"Scanning {len(course_codes)} courses for assignments...")

        # Concurrent scan
        items = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_scan_course, token, cc): cc for cc in course_codes}
            for f in as_completed(futures):
                course_items = f.result()
                if course_items:
                    items.extend(course_items)

        items.sort(key=lambda x: (0 if x["due_ts"] else 1, x["due_ts"] or ""))
        logger.info(f"Fetched {len(items)} assignments from {len(course_codes)} courses")

        # Save cache
        cache_data = {"_ts": time_module.time(), "_user": zxm_username, "items": items}
        write_json_file(cache_file, cache_data)

    # Filter by course_code if provided
    if course_code:
        items = [i for i in items if i.get("url", "").endswith(f"courseCode={course_code}")]

    return {"ok": True, "items": items, "cached": cached is not None}


# ---- State management ----

def load_state(username: str) -> dict:
    return _state_store.load(username)


def save_state(username: str, state: dict):
    _state_store.save(username, state)


def update_state(username: str, action: str, item_id) -> dict:
    """Apply hide/unhide/highlight/unhighlight."""
    return _state_store.update(username, action, item_id)
