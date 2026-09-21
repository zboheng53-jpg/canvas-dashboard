"""Ketangpai (课堂派) client for canvas-dashboard.

Login flows:
  1. Phone + SMS:
     - POST /UserApi/sendCode (optionally with captcha from /UserApi/getFigureCode)
     - POST /UserApi/loginByMobile with {mobile, code} to get token
  2. Account + Password:
     - POST /UserApi/login with {email, password} to get token
  3. Token usage:
     - Subsequent requests send HTTP Header "token: <token>"
"""
from __future__ import annotations

import base64
import json
import logging
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import settings
from platform_state import PlatformStateStore
from storage import load_or_create_bytes, read_json_file, write_json_file
from user_paths import DATA_DIR, user_dir

logger = logging.getLogger(__name__)

BASE_URL = settings.KETANGPAI_BASE_URL
WEB_URL = settings.KETANGPAI_WEB_URL
CST = timezone(timedelta(hours=8))
_state_store = PlatformStateStore(lambda username: user_dir(username) / "ketangpai_state.json", str)

KEY_FILE = DATA_DIR / ".encryption_key"

# In-memory token cache: {username: {"token": str, "expires_at": datetime}}
_token_cache: dict[str, dict] = {}


def _get_or_create_key() -> bytes:
    return load_or_create_bytes(KEY_FILE, Fernet.generate_key)


def _encrypt_token(plain: str) -> str:
    f = Fernet(_get_or_create_key())
    return f.encrypt(plain.encode()).decode()


def _decrypt_token(cipher: str) -> str:
    f = Fernet(_get_or_create_key())
    return f.decrypt(cipher.encode()).decode()


def _encrypt_password(password: str) -> str:
    """Encrypt password for Ketangpai using AES-128-CBC PKCS7 padding."""
    key = b"ktp4567890123456"
    iv = b"ktp4567890123456"
    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


# ---- SMS & Captcha ----

def get_figure_code() -> dict:
    """Fetch graphical captcha if required for SMS verification."""
    try:
        r = requests.post(
            f"{BASE_URL}/UserApi/getFigureCode",
            json={"reqtimestamp": int(time_module.time() * 1000)},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("status") == 1:
            res = data.get("data", {})
            img_url = res.get("url")
            sessionid = res.get("sessionid")
            image_data = None
            if img_url:
                try:
                    img_resp = requests.get(
                        img_url,
                        headers={"Referer": f"{WEB_URL}/"},
                        timeout=5,
                    )
                    if img_resp.status_code == 200:
                        content_type = img_resp.headers.get("Content-Type", "image/png")
                        b64 = base64.b64encode(img_resp.content).decode("ascii")
                        image_data = f"data:{content_type};base64,{b64}"
                except Exception as img_err:
                    logger.warning(f"Ketangpai fetch figure image failed: {img_err}")
            return {
                "ok": True,
                "url": img_url,
                "sessionid": sessionid,
                "image_data": image_data,
            }
        return {"ok": False, "error": data.get("message", "获取图形验证码失败")}
    except Exception as e:
        logger.error(f"Ketangpai get figure code failed: {e}")
        return {"ok": False, "error": f"获取图形验证码失败: {e}"}


def send_sms(phone: str, verify: str = "", sessionid: str = "") -> dict:
    """Send SMS verification code to phone."""
    try:
        payload = {
            "verify": verify,
            "mobile": phone,
            "sessionid": sessionid,
            "secondDomain": "",
            "type": "login",
            "reqtimestamp": int(time_module.time() * 1000),
        }
        r = requests.post(
            f"{BASE_URL}/UserApi/sendCode",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("status") == 1:
            return {"ok": True, "message": "验证码已发送"}
        err_msg = data.get("message", "发送失败")
        code = data.get("code")
        if code == 30106 or err_msg == "验证码输入错误":
            err_msg = "图形验证码计算错误，请重新输入"
        elif code in (30117, "30117"):
            err_msg = "该手机号未在课堂派注册"
        return {"ok": False, "error": err_msg, "code": code}
    except Exception as e:
        logger.error(f"Ketangpai SMS send failed: {e}")
        return {"ok": False, "error": f"发送失败: {e}"}


# ---- Login ----

def phone_login(username: str, phone: str, code: str) -> dict:
    """Login with mobile phone + SMS code."""
    try:
        payload = {
            "mobile": phone,
            "code": code,
            "remember": "1",
            "source_type": 1,
            "reqtimestamp": int(time_module.time() * 1000),
        }
        r = requests.post(
            f"{BASE_URL}/UserApi/loginByMobile",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("status") == 1:
            token = data["data"]["token"]
            _save_token(username, token)
            _token_cache[username] = {
                "token": token,
                "expires_at": datetime.now(CST) + timedelta(days=7),
            }
            return {"ok": True}
        return {"ok": False, "error": data.get("message", "登录失败")}
    except Exception as e:
        logger.error(f"Ketangpai phone login failed: {e}")
        return {"ok": False, "error": f"登录失败: {e}"}


def password_login(username: str, account: str, password: str) -> dict:
    """Login with account (email/phone) + password."""
    try:
        payload = {
            "email": account,
            "password": _encrypt_password(password),
            "encryption": 1,
            "remember": "1",
            "source_type": 1,
            "reqtimestamp": int(time_module.time() * 1000),
        }
        r = requests.post(
            f"{BASE_URL}/UserApi/login",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = r.json()
        if data.get("status") == 1:
            token = data["data"]["token"]
            _save_token(username, token)
            _token_cache[username] = {
                "token": token,
                "expires_at": datetime.now(CST) + timedelta(days=7),
            }
            return {"ok": True}
        return {"ok": False, "error": data.get("message", "登录失败")}
    except Exception as e:
        logger.error(f"Ketangpai password login failed: {e}")
        return {"ok": False, "error": f"登录失败: {e}"}


def _save_token(username: str, token: str):
    config_file = user_dir(username) / "config.json"
    config = read_json_file(config_file, {})
    config["ketangpai_token_encrypted"] = _encrypt_token(token)
    write_json_file(config_file, config)


def _load_token(username: str) -> str | None:
    config_file = user_dir(username) / "config.json"
    if not config_file.exists():
        return None
    try:
        config = read_json_file(config_file, {})
        enc = config.get("ketangpai_token_encrypted")
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
    if config_file.exists():
        try:
            config = read_json_file(config_file, {})
            config.pop("ketangpai_token_encrypted", None)
            write_json_file(config_file, config)
        except Exception:
            pass


def _get_token(username: str) -> str | None:
    cache = _token_cache.get(username, {})
    if cache.get("token") and cache.get("expires_at"):
        if datetime.now(CST) < cache["expires_at"]:
            return cache["token"]
    stored = _load_token(username)
    if stored:
        _token_cache[username] = {
            "token": stored,
            "expires_at": datetime.now(CST) + timedelta(days=7),
        }
        return stored
    return None


# ---- Courses & Assignments fetching ----

def fetch_courses(username: str) -> dict:
    """Fetch courses list for the current user."""
    token = _get_token(username)
    if not token:
        return {"ok": False, "error": "未登录课堂派"}
    try:
        r = requests.post(
            f"{BASE_URL}/courseApi/simpleLists",
            json={"reqtimestamp": int(time_module.time() * 1000)},
            headers={"token": token, "Content-Type": "application/json"},
            timeout=15,
        )
        data = r.json()
        if data.get("status") == 1:
            raw_lists = data.get("data", {}).get("lists", [])
            raw_top = data.get("data", {}).get("toplists", [])
            seen = set()
            courses = []
            for item in raw_top + raw_lists:
                cid = item.get("id")
                if cid and cid not in seen:
                    seen.add(cid)
                    courses.append({
                        "id": cid,
                        "coursename": item.get("coursename", ""),
                        "classname": item.get("classname", ""),
                        "semester": item.get("semester", ""),
                        "term": item.get("term", ""),
                        "fixTerm": str(item.get("fixTerm", "")),
                        "role": item.get("role", 0),
                        "classending": str(item.get("classending", "0")),
                    })
            return {"ok": True, "courses": courses}
        return {"ok": False, "error": data.get("message", "获取课程失败")}
    except Exception as e:
        logger.error(f"Fetch ketangpai courses failed: {e}")
        return {"ok": False, "error": f"获取课程失败: {e}"}


def _parse_ketangpai_time(val) -> tuple[str, str, str | None]:
    """Parse timestamp int/str or datetime string to (due_str, due_date, due_ts)."""
    if not val:
        return "", "", None
    dt = None
    if isinstance(val, (int, float)):
        ts = val / 1000 if val > 1e11 else val
        try:
            dt = datetime.fromtimestamp(ts, tz=CST)
        except (ValueError, OSError):
            pass
    elif isinstance(val, str):
        val = val.strip()
        if val.isdigit():
            n = int(val)
            ts = n / 1000 if n > 1e11 else n
            try:
                dt = datetime.fromtimestamp(ts, tz=CST)
            except (ValueError, OSError):
                pass
        else:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(val, fmt).replace(tzinfo=CST)
                    break
                except ValueError:
                    continue
            if dt is None:
                try:
                    dt = datetime.fromisoformat(val)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=CST)
                except ValueError:
                    pass

    if dt:
        return dt.strftime("%m-%d %H:%M"), dt.strftime("%Y-%m-%d %H:%M:%S"), dt.isoformat()
    return "", "", None


def _parse_assignment(rec: dict, course_id: str, course_name: str) -> dict | None:
    """Parse homework record (contenttype=4)."""
    title = rec.get("title", "未命名作业")
    raw_id = rec.get("id", "")
    endtime = rec.get("endtime")
    mstatus = rec.get("mstatus", 0)

    is_submitted = mstatus in (1, 2)
    if is_submitted:
        return None

    due_str, due_date, due_ts = _parse_ketangpai_time(endtime)

    return {
        "id": f"ktp_hw_{raw_id}",
        "title": title,
        "course": course_name,
        "due_str": due_str,
        "due_date": due_date,
        "due_ts": due_ts,
        "type": "作业",
        "type_raw": "assignment",
        "url": f"{WEB_URL}/courseHome?courseId={course_id}&tabActive=4",
        "submitted": False,
        "mstatus": mstatus,
    }


def _parse_test(rec: dict, course_id: str, course_name: str) -> dict | None:
    """Parse test/exam record (contenttype=6)."""
    title = rec.get("title", "随堂测试")
    raw_id = rec.get("id", "")
    endtime = rec.get("endtime")
    submit_state = rec.get("submit_state")
    over = rec.get("over", 0)

    is_submitted = (submit_state not in (0, None)) or (over == 1)
    if is_submitted:
        return None

    due_str, due_date, due_ts = _parse_ketangpai_time(endtime)

    return {
        "id": f"ktp_test_{raw_id}",
        "title": title,
        "course": course_name,
        "due_str": due_str,
        "due_date": due_date,
        "due_ts": due_ts,
        "type": "测验",
        "type_raw": "exam",
        "url": f"{WEB_URL}/courseHome?courseId={course_id}&tabActive=6",
        "submitted": False,
    }


def _scan_course_content(token: str, course_id: str, course_name: str, content_type: int) -> list[dict] | None:
    """Fetch homework or tests for one course."""
    items = []
    page = 1
    max_pages = 5

    while page <= max_pages:
        try:
            payload = {
                "courseid": course_id,
                "courserole": 0,
                "contenttype": content_type,
                "dirid": "0",
                "lessonlink": [],
                "desc": "3",
                "page": page,
                "limit": 50,
                "sort": [],
                "reqtimestamp": int(time_module.time() * 1000),
            }
            r = requests.post(
                f"{BASE_URL}/FutureV2/CourseMeans/getCourseContent",
                json=payload,
                headers={"token": token, "Content-Type": "application/json"},
                timeout=15,
            )
            data = r.json()
            if data.get("status") != 1:
                return None
            records = data.get("data", {}).get("list") or data.get("data", {}).get("lists") or []
            for rec in records:
                parsed = _parse_assignment(rec, course_id, course_name) if content_type == 4 else _parse_test(rec, course_id, course_name)
                if parsed is not None:
                    items.append(parsed)

            page_total = data.get("data", {}).get("pageTotal", 1)
            if page >= page_total:
                break
            page += 1
        except Exception as e:
            logger.warning(f"Failed to scan course {course_id} content {content_type}: {e}")
            return None

    return items


CACHE_TTL = 30 * 60  # 30 minutes


def fetch_assignments(username: str, course_id: str = None, force_fetch: bool = False) -> dict:
    """Fetch assignments & tests from Ketangpai, scanning active courses.

    Results are cached for 30 minutes. Pass course_id to filter.
    """
    token = _get_token(username)
    cache_file = user_dir(username) / "ketangpai_cache.json"

    if not token:
        cached = _fallback_assignments_cache(cache_file, course_id)
        if cached is not None:
            cached.update(disconnected=True, need_setup=True, error="课堂派已断开，正在显示最后一次同步数据")
            return cached
        return {"ok": False, "error": "未登录，请先登录课堂派", "items": [], "need_setup": True}

    # Check memory/file cache
    cached = None
    if not force_fetch and cache_file.exists():
        try:
            raw = read_json_file(cache_file, {})
            ts = raw.get("_ts", 0)
            if time_module.time() - ts < CACHE_TTL:
                cached = raw
                logger.info(f"Using cached Ketangpai assignments ({len(raw.get('items', []))} items)")
        except Exception:
            pass

    if cached is not None:
        items = cached.get("items", [])
    else:
        courses_res = fetch_courses(username)
        if not courses_res.get("ok"):
            fallback = _fallback_assignments_cache(cache_file, course_id)
            if fallback is not None:
                return fallback
            return {"ok": False, "error": courses_res.get("error", "获取课程列表失败"), "items": []}

        courses = courses_res.get("courses", [])
        if not courses:
            write_json_file(cache_file, {"_ts": time_module.time(), "items": [], "sync_complete": True})
            return {"ok": True, "items": [], "cached": False, "sync_complete": True}

        # Filter active courses:
        # Highest fixTerm semester courses PLUS any courses with classending == "0"
        fix_terms = [c["fixTerm"] for c in courses if c.get("fixTerm")]
        latest_term = max(fix_terms) if fix_terms else ""

        active_courses = [
            c for c in courses
            if (latest_term and c.get("fixTerm") == latest_term) or c.get("classending") == "0"
        ]
        if not active_courses:
            active_courses = courses

        logger.info(f"Scanning {len(active_courses)} active Ketangpai courses...")

        # Concurrently fetch homework (contenttype=4) and tests (contenttype=6)
        tasks = []
        for c in active_courses:
            cid = c["id"]
            cname = c["coursename"]
            tasks.append((cid, cname, 4))
            tasks.append((cid, cname, 6))

        items = []
        complete = True
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_scan_course_content, token, cid, cname, ctype): (cid, cname, ctype)
                for cid, cname, ctype in tasks
            }
            for f in as_completed(futures):
                try:
                    course_items = f.result()
                except Exception:
                    course_items = None
                if course_items is None:
                    complete = False
                    continue
                if course_items:
                    items.extend(course_items)

        if not complete:
            fallback = _fallback_assignments_cache(cache_file, course_id)
            if fallback is not None:
                return fallback
            return {"ok": False, "error": "课程任务同步不完整，已保留上次可信数据", "items": [], "sync_complete": False}

        # Deduplicate and sort by due_ts
        seen_ids = set()
        unique_items = []
        for it in items:
            if it["id"] not in seen_ids:
                seen_ids.add(it["id"])
                unique_items.append(it)

        unique_items.sort(key=lambda x: (0 if x["due_ts"] else 1, x["due_ts"] or ""))
        items = unique_items

        # Save cache atomically
        write_json_file(cache_file, {
            "_ts": time_module.time(),
            "items": items,
            "sync_complete": True,
        })

    if course_id:
        items = [i for i in items if f"courseId={course_id}" in i.get("url", "")]

    return {
        "ok": True,
        "items": items,
        "cached": cached is not None,
        "sync_complete": bool(cached.get("sync_complete", True)) if cached is not None else True,
    }


def _fallback_assignments_cache(cache_file, course_id):
    if not cache_file.exists():
        return None
    try:
        cached = read_json_file(cache_file, {})
        items = list(cached.get("items", []))
        if course_id:
            items = [i for i in items if f"courseId={course_id}" in i.get("url", "")]
        return {"ok": True, "items": items, "cached": True, "stale": True, "sync_complete": False}
    except Exception:
        return None


# ---- State management ----

def load_state(username: str) -> dict:
    return _state_store.load(username)


def save_state(username: str, state: dict):
    _state_store.save(username, state)


def update_state(username: str, action: str, item_id: str) -> dict:
    """Apply hide/unhide/highlight/unhighlight."""
    return _state_store.update(username, action, item_id)


def update_override(username: str, item_id: str, patch=None, restore=False) -> dict:
    return _state_store.update_override(username, item_id, patch, restore)
