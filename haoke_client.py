"""Haoke Platform (Zhitu AI Haoke) client for Tongji University.

Login flow:
  1. POST /api/auth/getRsaKey  with {"encType":"aes", "requestId"} -> {keyId, key}
  2. AES-256-ECB encrypt password with the server-provided key (Base64 decoded)
  3. POST /api/auth/userNoLogin -> token in response body and haoke-token cookie
  4. Use token as Authorization: Bearer for subsequent API calls
"""
import json
import logging
import threading
import time
import uuid
import base64
from datetime import datetime, timezone, timedelta

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from cryptography.fernet import Fernet

import settings
from platform_state import PlatformStateStore
from storage import read_json_file, write_json_file
from user_paths import user_dir, DATA_DIR

logger = logging.getLogger(__name__)

BASE_URL = settings.HAOKE_BASE_URL
TENANT_ID = settings.HAOKE_TENANT_ID  # Tongji University tenant ID
CST = timezone(timedelta(hours=8))
_state_store = PlatformStateStore(lambda username: user_dir(username) / "haoke_state.json", int)

TASK_TYPE_MAP = {
    10: "签到", 20: "资料", 25: "链接", 30: "作业",
    35: "写作", 40: "测验", 45: "问卷", 50: "讨论",
    60: "考试", 70: "通知", 80: "线下活动",
}

KEY_FILE = DATA_DIR / ".encryption_key"

# In-memory token cache, keyed by username
_token_cache: dict[str, dict] = {}
HAOKE_CACHE_TTL_SECONDS = 30 * 60
_refreshing_users: set[str] = set()
_refresh_lock = threading.Lock()

# ---- Fernet key management for local password encryption ----


def _get_or_create_key():
    """Load or generate a Fernet key for local password encryption (shared across accounts)."""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(key)
    return key


def _encrypt_password_local(plain: str) -> str:
    """Encrypt password for local storage using Fernet."""
    f = Fernet(_get_or_create_key())
    return f.encrypt(plain.encode()).decode()


def _decrypt_password_local(cipher: str) -> str:
    """Decrypt locally stored password using Fernet."""
    f = Fernet(_get_or_create_key())
    return f.decrypt(cipher.encode()).decode()


# ---- AES-ECB encryption for network transmission ----


def _encrypt_password_aes(plain: str, key_b64: str) -> str:
    """Encrypt password with AES-256-ECB using the server-provided key."""
    key = base64.b64decode(key_b64)
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(plain.encode(), 16))
    return base64.b64encode(encrypted).decode()


# ---- Credentials management ----


def has_credentials(username: str) -> bool:
    """Check if haoke credentials are configured."""
    config_file = user_dir(username) / "config.json"
    config = read_json_file(config_file, {})
    return bool(config.get("haoke_username") and config.get("haoke_password_encrypted"))


def save_credentials(username: str, haoke_username: str, password: str):
    """Save encrypted haoke credentials."""
    config_file = user_dir(username) / "config.json"
    config = read_json_file(config_file, {})
    config["haoke_username"] = haoke_username.strip()
    config["haoke_password_encrypted"] = _encrypt_password_local(password)
    write_json_file(config_file, config)
    # Invalidate token cache
    _token_cache.pop(username, None)


def _get_credentials(username: str):
    """Get decrypted haoke credentials."""
    config_file = user_dir(username) / "config.json"
    if not config_file.exists():
        return None, None
    try:
        config = read_json_file(config_file, {})
        haoke_username = config.get("haoke_username")
        enc_pwd = config.get("haoke_password_encrypted")
        if haoke_username and enc_pwd:
            return haoke_username, _decrypt_password_local(enc_pwd)
    except Exception:
        pass
    return None, None


# ---- Token management ----


def _login(haoke_username: str, password: str) -> str | None:
    """Login to haoke platform and return token."""
    session = requests.Session()
    session.headers.update({
        "__tenant__": "tongji",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    # Step 1: Get AES key from server
    logger.info("Requesting AES key from haoke...")
    rid = str(uuid.uuid4())
    try:
        r = session.post(
            f"{BASE_URL}/api/auth/getRsaKey",
            json={"encType": "aes", "requestId": rid},
            timeout=15,
        )
        rsa_data = r.json()
        if rsa_data.get("code") != 200:
            logger.error(f"getRsaKey failed: {rsa_data.get('message')}")
            return None
        key_id = rsa_data["data"]["keyId"]
        aes_key_b64 = rsa_data["data"]["key"]
    except Exception as e:
        logger.error(f"getRsaKey error: {e}")
        return None

    # Step 2: Encrypt password with server AES key
    encrypted_pwd = _encrypt_password_aes(password, aes_key_b64)

    # Step 3: Login
    logger.info(f"Logging in as {haoke_username}...")
    rid = str(uuid.uuid4())
    try:
        r = session.post(
            f"{BASE_URL}/api/auth/userNoLogin",
            json={
                "autoLogin": False,
                "tenantId": TENANT_ID,
                "userNo": haoke_username,
                "userPassword": encrypted_pwd,
                "keyId": key_id,
                "deviceType": "pc",
                "encType": "aes",
                "requestId": rid,
            },
            timeout=15,
        )
        login_data = r.json()
        if login_data.get("code") != 200:
            msg = login_data.get("message", "登录失败")
            logger.error(f"Login failed: {msg}")
            return None

        # Extract token from response
        token = login_data.get("data", {}).get("token")
        if not token:
            # Try from cookie
            token = session.cookies.get("haoke-token")

        if token:
            logger.info("Login successful, token obtained")
            return token
        else:
            logger.error("Login succeeded but no token found")
            return None

    except Exception as e:
        logger.error(f"Login error: {e}")
        return None


def _get_token(username: str) -> str | None:
    """Get a valid token, refreshing if necessary (2 hour cache)."""
    cache = _token_cache.get(username, {})

    # Check cache
    if cache.get("token") and cache.get("expires_at"):
        if datetime.now(CST) < cache["expires_at"]:
            return cache["token"]

    # Need to login
    haoke_username, password = _get_credentials(username)
    if not haoke_username or not password:
        return None

    token = _login(haoke_username, password)
    if token:
        _token_cache[username] = {"token": token, "expires_at": datetime.now(CST) + timedelta(hours=2)}
        return token

    return None


# ---- Todo fetching ----


def fetch_haoke_todos(username: str) -> dict:
    """Fetch todo items from haoke platform.

    Returns: {ok, data, cached, need_setup, error}
    """
    if not has_credentials(username):
        return {"ok": False, "error": "请先设置好课平台账号密码", "data": [], "need_setup": True}

    token = _get_token(username)
    if not token:
        return {"ok": False, "error": "好课平台登录失败，请检查账号密码", "data": []}

    try:
        items = _fetch_all_todos(token)
        # Cache on success
        cache_file = user_dir(username) / "haoke_cache.json"
        write_json_file(cache_file, items)
        return {"ok": True, "data": items, "cached": False}
    except Exception as e:
        logger.warning(f"Haoke todo fetch failed: {e}")
        return _fallback_cache(username)


def _fetch_my_courses(token: str) -> list[dict]:
    """Fetch the user's enrolled courses with classId and instanceId."""
    headers = {
        "__tenant__": "tongji",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0",
    }
    try:
        r = requests.post(
            f"{BASE_URL}/api/teach/instance/listMyClass",
            json={"requestId": str(uuid.uuid4())},
            headers=headers,
            timeout=15,
        )
        data = r.json()
        if data.get("code") == 200:
            courses = data.get("data", {}).get("teachClassResponseList", [])
            logger.info(f"Fetched {len(courses)} courses from haoke")
            return courses
        else:
            logger.warning(f"listMyClass failed: code={data.get('code')}")
            return []
    except Exception as e:
        logger.warning(f"listMyClass error: {e}")
        return []


def _fetch_all_todos(token: str) -> list[dict]:
    """Fetch todos from all relevant haoke API endpoints, scoped to each course."""
    headers = {
        "__tenant__": "tongji",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0",
    }
    session = requests.Session()
    session.headers.update(headers)

    # First, get the user's courses
    courses = _fetch_my_courses(token)
    if not courses:
        # Fallback: try without course context (unlikely to return data)
        logger.warning("No courses found, trying unscoped task endpoints as fallback")
        courses = [{"classId": None, "instanceId": None, "instanceName": ""}]

    all_items = []
    seen_task_ids = set()

    for course in courses:
        class_id = course.get("classId")
        instance_id = course.get("instanceId")
        course_name = course.get("instanceName") or course.get("className") or ""

        # 1. listTask with classId (flat task list)
        if class_id:
            try:
                body = {"page": {"pageNo": 1, "pageSize": 200}, "classId": class_id, "requestId": str(uuid.uuid4())}
                r = session.post(f"{BASE_URL}/api/learn/task/listTask", json=body, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("code") == 200:
                        row_list = data.get("data", {}).get("rowList", [])
                        for task in row_list:
                            tid = task.get("taskId")
                            if tid and tid not in seen_task_ids:
                                seen_task_ids.add(tid)
                                norm = _normalize_task(task, course_name)
                                if norm:
                                    all_items.append(norm)
                        logger.info(f"Fetched {len(row_list)} tasks via listTask for course {course_name}")
                    else:
                        logger.warning(f"listTask for classId={class_id}: code={data.get('code')}")
            except Exception as e:
                logger.warning(f"listTask failed for classId={class_id}: {e}")

        # 2. listEasyTask with classId
        if class_id:
            try:
                body = {"page": {"pageNo": 1, "pageSize": 200}, "classId": class_id, "requestId": str(uuid.uuid4())}
                r = session.post(f"{BASE_URL}/api/learn/task/listEasyTask", json=body, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("code") == 200:
                        row_list = data.get("data", {}).get("rowList", [])
                        for task in row_list:
                            tid = task.get("taskId")
                            if tid and tid not in seen_task_ids:
                                seen_task_ids.add(tid)
                                norm = _normalize_task(task, course_name)
                                if norm:
                                    all_items.append(norm)
                        logger.info(f"Fetched {len(row_list)} tasks via listEasyTask for course {course_name}")
            except Exception as e:
                logger.warning(f"listEasyTask failed for classId={class_id}: {e}")

        # 3. listUnitTask with instanceId (chapter-organized tasks)
        if instance_id:
            try:
                body = {"instanceId": instance_id, "requestId": str(uuid.uuid4())}
                r = session.post(f"{BASE_URL}/api/learn/task/listUnitTask", json=body, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("code") == 200:
                        chapter_list = data.get("data", {}).get("chapterList", [])
                        for chapter in chapter_list:
                            for lecture in chapter.get("lectureList", []):
                                for task in lecture.get("taskList", []):
                                    tid = task.get("taskId")
                                    if tid and tid not in seen_task_ids:
                                        seen_task_ids.add(tid)
                                        norm = _normalize_task(task, course_name)
                                        if norm:
                                            all_items.append(norm)
                        logger.info(f"Fetched unit tasks for course {course_name} across {len(chapter_list)} chapters")
            except Exception as e:
                logger.warning(f"listUnitTask failed for instanceId={instance_id}: {e}")

    # Deduplicate and sort
    all_items.sort(key=lambda x: (0 if x["due_ts"] else 1, x["due_ts"] or ""))
    return all_items


def _normalize_task(raw: dict, course_name: str) -> dict:
    """Normalize a single haoke task into the unified todo format."""

    title = (
        raw.get("taskName")
        or raw.get("taskTitle")
        or raw.get("title")
        or raw.get("name")
        or raw.get("courseTaskName")
        or "未命名任务"
    )

    item_id = raw.get("taskId") or raw.get("id") or raw.get("courseTaskId") or abs(hash(str(raw))) % 1000000

    # Task type: numeric code from API → human readable
    raw_type = raw.get("taskType")
    if isinstance(raw_type, int):
        type_name = TASK_TYPE_MAP.get(raw_type, f"任务({raw_type})")
    else:
        type_name = raw.get("taskTypeName") or raw.get("typeName") or "任务"

    # Due date — check endTime first (the actual field name)
    due_str = ""
    due_ts = None
    today = datetime.now(CST).replace(hour=0, minute=0, second=0, microsecond=0)
    for date_field in ("endTime", "gmtEnd", "endDate", "dueDate", "deadline", "expireTime", "limitTime"):
        raw_date = raw.get(date_field)
        if raw_date:
            due_ts = _parse_date(raw_date)
            if due_ts:
                break

    if due_ts:
        # Year >= 9999 is a sentinel for "no deadline"
        if due_ts.year >= 9999:
            return None  # sentinel — no deadline
        if due_ts < today:
            return None  # expired
        elif due_ts.hour == 0 and due_ts.minute == 0:
            due_str = due_ts.strftime("%m-%d")
        else:
            due_str = due_ts.strftime("%m-%d %H:%M")
    else:
        return None  # no due date

    # URL
    url = ""
    instance_id = raw.get("instanceId") or ""
    task_id = raw.get("courseTaskId") or raw.get("taskId") or item_id
    if instance_id and task_id:
        url = f"{BASE_URL}/student/course/{instance_id}/home?taskId={task_id}"

    return {
        "id": item_id,
        "title": str(title),
        "course": str(course_name),
        "due_str": due_str,
        "due_ts": due_ts.isoformat() if due_ts else None,
        "type": type_name,
        "type_raw": str(raw_type),
        "url": url,
    }


def _parse_haoke_response(data: dict, endpoint: str) -> list[dict]:
    """Parse haoke API response (deprecated — kept for potential fallback)."""
    return []


def _parse_date(raw) -> datetime | None:
    """Parse a date/time value from the API into a CST datetime."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # Unix timestamp (ms or seconds)
        if raw > 1e12:
            raw = raw / 1000
        dt = datetime.fromtimestamp(raw, tz=CST)
        return dt
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        # Try ISO format
        try:
            # Handle various ISO formats
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
            else:
                dt = dt.astimezone(CST)
            return dt
        except ValueError:
            pass
        # Try common formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.replace(tzinfo=CST)
            except ValueError:
                continue
    return None


# ---- Cache ----


def _cache_file(username: str):
    return user_dir(username) / "haoke_cache.json"


def get_cached_todos(username: str, now: float | None = None) -> dict | None:
    """Load cached haoke todos with freshness metadata, if cache exists."""
    cache_file = _cache_file(username)
    if not cache_file.exists():
        return None
    items = read_json_file(cache_file, [])
    fetched_at = cache_file.stat().st_mtime
    if now is None:
        now = time.time()
    return {
        "ok": True,
        "data": items,
        "cached": True,
        "fetched_at": fetched_at,
        "stale": now - fetched_at > HAOKE_CACHE_TTL_SECONDS,
    }


def _run_background_refresh(username: str):
    try:
        fetch_haoke_todos(username)
    finally:
        with _refresh_lock:
            _refreshing_users.discard(username)


def start_background_refresh(username: str) -> bool:
    """Start one background haoke refresh for a user if none is active."""
    with _refresh_lock:
        if username in _refreshing_users:
            return False
        _refreshing_users.add(username)
    try:
        thread = threading.Thread(target=_run_background_refresh, args=(username,), daemon=True)
        thread.start()
        return True
    except Exception:
        with _refresh_lock:
            _refreshing_users.discard(username)
        raise


def _fallback_cache(username: str) -> dict:
    """Return cached haoke data if available."""
    cache_file = user_dir(username) / "haoke_cache.json"
    if cache_file.exists():
        try:
            items = read_json_file(cache_file, [])
            return {"ok": True, "data": items, "cached": True}
        except Exception:
            pass
    return {"ok": False, "error": "无法获取好课数据，且无缓存数据", "data": []}


# ---- State management (hidden/highlighted) ----


def load_state(username: str) -> dict:
    """Load hidden/highlighted haoke item IDs."""
    return _state_store.load(username)


def save_state(username: str, state: dict):
    """Save haoke state."""
    _state_store.save(username, state)


def update_state(username: str, action: str, item_id: int) -> dict:
    """Apply a state action: hide, unhide, highlight, unhighlight."""
    return _state_store.update(username, action, item_id)
