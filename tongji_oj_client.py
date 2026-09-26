"""Tongji OJ (同济大学竞教融合实训平台 oj.tongji.edu.cn) Client.

Supports:
  1. Tongji Unified Authentication (同济统一身份认证登录 Unified_Certification via iam.tongji.edu.cn)
  2. Local OJ username/password login fallback (U_Login)
  3. Read-only assignment & submission list scraping from:
     - GET /index.php/assignments
     - GET /index.php/submissions/final/course/all
     Strictly never opens individual problem pages (/assignments/problems_list/... or /problems/...)
     and never submits any code or form on assignments.
"""

import base64
import html as html_module
from html.parser import HTMLParser
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

import settings
from platform_state import PlatformStateStore
from storage import locked_json_update, read_json_file, write_json_file
from user_paths import DATA_DIR, user_dir

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

OJ_BASE_URL = "https://oj.tongji.edu.cn"
OJ_LOGIN_URL = f"{OJ_BASE_URL}/index.php/login"
OJ_IAM_LOGIN_URL = f"{OJ_BASE_URL}/index.php/login/Unified_Certification"
OJ_LOCAL_LOGIN_URL = f"{OJ_BASE_URL}/index.php/login/U_Login"
OJ_DASHBOARD_URL = f"{OJ_BASE_URL}/index.php/dashboard"
OJ_ASSIGNMENTS_URL = f"{OJ_BASE_URL}/index.php/assignments"
OJ_FINAL_SUBMISSIONS_URL = f"{OJ_BASE_URL}/index.php/submissions/final/course/all"

IAM_BASE_URL = "https://iam.tongji.edu.cn"
IAM_ENTITY_ID = "SYS20240302"
# Public key from https://iam.tongji.edu.cn/idp/themes/default/js/main/crypt.js
IAM_RSA_PUBLIC_KEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC9t16RqQWUE/J1IyOfoNHc4r/h6RPnXcWTJ4I"
    "bhQVUsEqMMm65F0hiytAgozXmVw68yPJywbpblDrx9zl1wdRcdHCoUvmPdr9/oCQtpQyVc7BXZI"
    "N6wJlD6MTeMeni+N0toNPxfXjiAawjNHGZZuT8wQpNEMwsVyJ/lonXaVdGZwIDAQAB"
)

KEY_FILE = DATA_DIR / ".encryption_key"
CACHE_TTL = settings.TONGJIOJ_CACHE_TTL_SECONDS

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

IAM_AJAX_ACCEPT = "application/json, text/javascript, */*; q=0.01"

# In-memory session cookie cache per username
_cookie_cache: dict[str, dict[str, str]] = {}
# Short-lived pending IAM second-factor (加强认证) sessions per username
_pending_iam_sessions: dict[str, dict] = {}


def _config_file(username: str):
    return user_dir(username) / "config.json"


def _cache_file(username: str):
    return user_dir(username) / "tongjioj_cache.json"


# ---- Encryption helpers ----

def _get_fernet() -> Fernet:
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
    return Fernet(key)


def _encrypt_rsa_password(plain_password: str, public_key_b64: str | None = None) -> str:
    """Encrypt password with Tongji IAM's RSA public key (PKCS#1 v1.5 + Base64)."""
    der_bytes = base64.b64decode(public_key_b64 or IAM_RSA_PUBLIC_KEY_B64)
    pub_key = serialization.load_der_public_key(der_bytes)
    encrypted = pub_key.encrypt(plain_password.encode("utf-8"), asym_padding.PKCS1v15())
    return base64.b64encode(encrypted).decode("ascii")


# ---- Credential & Cookie storage ----

def save_credentials(
    username: str,
    account: str,
    password: str,
    login_mode: str = "iam",
    cookies: dict[str, str] | None = None,
):
    """Save encrypted Tongji OJ credentials and optional session cookies."""
    f = _get_fernet()
    cred_payload = json.dumps(
        {"username": account, "password": password, "login_mode": login_mode},
        ensure_ascii=False,
    )
    cred_encrypted = f.encrypt(cred_payload.encode("utf-8")).decode("ascii")

    cookie_encrypted = None
    if cookies:
        _cookie_cache[username] = dict(cookies)
        cookie_payload = json.dumps(cookies, ensure_ascii=False)
        cookie_encrypted = f.encrypt(cookie_payload.encode("utf-8")).decode("ascii")

    def _update(cfg):
        cfg["tongjioj_credentials_encrypted"] = cred_encrypted
        if cookie_encrypted is not None:
            cfg["tongjioj_cookies_encrypted"] = cookie_encrypted
        return cfg

    locked_json_update(_config_file(username), {}, _update)
    try:
        _cache_file(username).unlink(missing_ok=True)
    except Exception:
        pass


def _save_cookies(username: str, cookies: dict[str, str]):
    if not cookies:
        return
    _cookie_cache[username] = dict(cookies)
    f = _get_fernet()
    cookie_payload = json.dumps(cookies, ensure_ascii=False)
    cookie_encrypted = f.encrypt(cookie_payload.encode("utf-8")).decode("ascii")

    def _update(cfg):
        cfg["tongjioj_cookies_encrypted"] = cookie_encrypted
        return cfg

    locked_json_update(_config_file(username), {}, _update)


def load_credentials(username: str) -> dict | None:
    """Load and decrypt stored credentials for `username`."""
    config_file = _config_file(username)
    if not config_file.exists():
        return None
    cfg = read_json_file(config_file, {})
    enc = cfg.get("tongjioj_credentials_encrypted")
    if not enc:
        return None
    try:
        f = _get_fernet()
        raw = f.decrypt(enc.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("username") and data.get("password"):
            return {
                "username": str(data["username"]),
                "password": str(data["password"]),
                "login_mode": str(data.get("login_mode") or "iam"),
            }
    except Exception as e:
        logger.warning(f"Failed to decrypt Tongji OJ credentials for {username}: {e}")
    return None


def _load_cookies(username: str) -> dict[str, str] | None:
    if username in _cookie_cache:
        return dict(_cookie_cache[username])
    config_file = _config_file(username)
    if not config_file.exists():
        return None
    cfg = read_json_file(config_file, {})
    enc = cfg.get("tongjioj_cookies_encrypted")
    if not enc:
        return None
    try:
        f = _get_fernet()
        raw = f.decrypt(enc.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and data:
            _cookie_cache[username] = data
            return dict(data)
    except Exception as e:
        logger.warning(f"Failed to decrypt Tongji OJ cookies for {username}: {e}")
    return None


def has_credentials(username: str) -> bool:
    """Return True if user has stored credentials or session cookies."""
    if username in _cookie_cache:
        return True
    config_file = _config_file(username)
    if not config_file.exists():
        return False
    cfg = read_json_file(config_file, {})
    return bool(cfg.get("tongjioj_credentials_encrypted") or cfg.get("tongjioj_cookies_encrypted"))


def logout(username: str):
    """Clear stored credentials and session cookies."""
    _cookie_cache.pop(username, None)
    config_file = _config_file(username)
    if config_file.exists():
        def _clear(cfg):
            cfg.pop("tongjioj_credentials_encrypted", None)
            cfg.pop("tongjioj_cookies_encrypted", None)
            cfg.pop("tongjioj_selected_course", None)
            cfg.pop("tongjioj_courses", None)
            return cfg

        locked_json_update(config_file, {}, _clear)


def get_selected_course(username: str) -> str | None:
    config_file = _config_file(username)
    if not config_file.exists():
        return None
    cfg = read_json_file(config_file, {})
    return cfg.get("tongjioj_selected_course") or None


def set_selected_course(username: str, course_id: str | None):
    def _update(cfg):
        cfg["tongjioj_selected_course"] = course_id or ""
        return cfg

    locked_json_update(_config_file(username), {}, _update)


def get_saved_courses(username: str) -> list[dict]:
    config_file = _config_file(username)
    if config_file.exists():
        cfg = read_json_file(config_file, {})
        if isinstance(cfg.get("tongjioj_courses"), list):
            return cfg["tongjioj_courses"]
    cache_file = _cache_file(username)
    if cache_file.exists():
        cached = read_json_file(cache_file, {})
        if isinstance(cached, dict) and isinstance(cached.get("courses"), list):
            return cached["courses"]
    return []


def _save_courses(username: str, courses: list[dict]):
    def _update(cfg):
        cfg["tongjioj_courses"] = courses
        return cfg

    locked_json_update(_config_file(username), {}, _update)


# ---- Authentication Flows ----

def _extract_iam_page_params(html: str, current_url: str) -> tuple[str | None, str | None]:
    """Extract (authnLcKey, spAuthChainCode) from Tongji IAM ActionAuthChain HTML."""
    m_key = re.search(r"authnLcKey=([A-Za-z0-9_-]+)", current_url)
    if not m_key:
        m_key = re.search(r'id=["\']authnLcKey["\'][^>]*value=["\']([^"\']+)["\']', html)
    authn_lc_key = m_key.group(1) if m_key else None

    # spAuthChainCode1 is injected via inline script: $("#spAuthChainCode1").val('4c1eb8...');
    m_chain = re.search(r'\$\(["\']#spAuthChainCode1?["\']\)\.val\(["\']([A-Za-z0-9]+)["\']\)', html)
    if not m_chain:
        m_chain = re.search(r'id=["\']spAuthChainCode(?:1|24)?["\'][^>]*value=["\']([A-Za-z0-9]+)["\']', html)
    sp_chain_code = m_chain.group(1) if m_chain else None
    return authn_lc_key, sp_chain_code


def _parse_iam_ajax_response(resp) -> dict | None:
    """Parse IAM AJAX response as JSON, or fall back to <JSONObject> XML if returned."""
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    text = (getattr(resp, "text", "") or "").strip()
    if text.startswith("<JSONObject"):
        try:
            root = ElementTree.fromstring(text)
            return {child.tag: (child.text or "") for child in root}
        except Exception:
            pass
    return None


def _clean_iam_error(raw_msg: str | None, fallback: str = "学号或统一身份认证密码错误") -> str:
    if not raw_msg:
        return fallback
    text = html_module.unescape(str(raw_msg))
    text = re.sub(r"<br\s*/?>", "；", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[；;\s]+$", "", text.strip())
    return text or fallback


def _is_oj_authenticated_response(resp) -> bool:
    """Check whether a response from oj.tongji.edu.cn is an authenticated page (not login page)."""
    url = str(getattr(resp, "url", "") or "")
    text = getattr(resp, "text", "") or ""
    if "/index.php/login" in url:
        return False
    if 'action="https://oj.tongji.edu.cn/index.php/login/U_Login"' in text:
        return False
    if "Unified_Certification" in text and "统一身份认证登录" in text and "dashboard" not in url:
        return False
    return resp.status_code == 200


def _session_cookies_dict(sess: requests.Session) -> dict[str, str]:
    cookies = {}
    for c in sess.cookies:
        if hasattr(c, "name") and hasattr(c, "value"):
            if "oj.tongji.edu.cn" in (getattr(c, "domain", "") or "") or c.name in ("shjsession", "shjcsrftoken", "PHPSESSID"):
                cookies[c.name] = c.value
    if not cookies:
        if hasattr(sess.cookies, "get_dict"):
            cookies = sess.cookies.get_dict()
        elif isinstance(sess.cookies, dict):
            cookies = dict(sess.cookies)
    return cookies


def iam_login(username: str, student_id: str, password: str) -> dict:
    """Authenticate to oj.tongji.edu.cn via Tongji Unified Authentication (Unified_Certification)."""
    student_id = (student_id or "").strip()
    if not student_id or not password:
        return {"ok": False, "error": "请输入学号/工号和统一身份认证密码"}

    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)

    try:
        # Step 1: Visit OJ Unified_Certification endpoint, which redirects to iam.tongji.edu.cn
        r1 = sess.get(OJ_IAM_LOGIN_URL, timeout=15, allow_redirects=True)
        if _is_oj_authenticated_response(r1) and "/index.php/dashboard" in str(r1.url):
            cookies = _session_cookies_dict(sess)
            save_credentials(username, student_id, password, login_mode="iam", cookies=cookies)
            return {"ok": True}

        authn_lc_key, sp_chain_code = _extract_iam_page_params(r1.text, str(r1.url))
        if not authn_lc_key or not sp_chain_code:
            logger.warning("Tongji IAM login page missing authnLcKey/spAuthChainCode: url=%s", r1.url)
            return {"ok": False, "error": "无法解析统一身份认证页面参数，请稍后重试"}

        encrypted_pwd = _encrypt_rsa_password(password)

        # Step 2: Check whether verification code is required
        try:
            vc_resp = sess.post(
                f"{IAM_BASE_URL}/idp/displayVerificationCode.do",
                data={
                    "j_username": student_id,
                    "j_authMethodID": "1",
                    "spAuthChainCode": sp_chain_code,
                },
                headers={
                    "Accept": IAM_AJAX_ACCEPT,
                    "Referer": str(r1.url),
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=10,
            )
            if vc_resp.text.strip().lower() == "true":
                return {
                    "ok": False,
                    "error": "统一身份认证当前触发图形验证码保护，请稍后重试或使用平台密码登录",
                }
        except Exception:
            pass

        # Step 3: AJAX pre-validation on ActionAuthChain
        action_url = f"{IAM_BASE_URL}/idp/authcenter/ActionAuthChain?authnLcKey={authn_lc_key}"
        form_payload = {
            "j_username": student_id,
            "j_password": encrypted_pwd,
            "j_checkcode": "请输入验证码",
            "op": "login",
            "spAuthChainCode": sp_chain_code,
            "authnLcKey": authn_lc_key,
        }
        r2 = sess.post(
            action_url,
            data=form_payload,
            headers={
                "Accept": IAM_AJAX_ACCEPT,
                "Referer": str(r1.url),
                "Origin": IAM_BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        auth_res = _parse_iam_ajax_response(r2)
        if not auth_res:
            return {"ok": False, "error": "统一身份认证返回格式异常，请稍后重试"}

        if str(auth_res.get("loginFailed")).lower() != "false":
            view = str(auth_res.get("view") or "")
            auth_list = str(auth_res.get("authList") or "")
            if view in ("biometrics", "4") or auth_list in ("sms", "email"):
                show_username = str(
                    auth_res.get("show_username")
                    or auth_res.get("showViewExcepUsername")
                    or auth_res.get("j_username")
                    or student_id
                )
                mobile = str(auth_res.get("mobile") or "")
                email = str(auth_res.get("email") or "")
                chain_code_24 = str(auth_res.get("currentAuChainCodeEx") or sp_chain_code)
                _pending_iam_sessions[username] = {
                    "session": sess,
                    "student_id": student_id,
                    "password": password,
                    "show_username": show_username,
                    "authn_lc_key": authn_lc_key,
                    "sp_chain_code": chain_code_24,
                    "referer": str(r1.url),
                    "mobile": mobile,
                    "email": email,
                    "created_at": time.time(),
                }
                auth_methods = []
                if mobile:
                    auth_methods.append({"type": "sms", "label": f"手机短信 ({mobile})"})
                if email:
                    auth_methods.append({"type": "email", "label": f"电子邮箱 ({email})"})
                if not auth_methods:
                    auth_methods.append({"type": "sms", "label": "手机短信验证码"})
                return {
                    "ok": False,
                    "need_second_auth": True,
                    "mobile": mobile,
                    "email": email,
                    "auth_methods": auth_methods,
                    "error": "陌生设备首次登录需进行加强认证，请点击「发送验证码」并输入收到的验证码完成登录",
                }
            raw_err = (
                auth_res.get("authnErrorTip")
                or auth_res.get("message")
                or auth_res.get("errorMsg")
            )
            return {"ok": False, "error": _clean_iam_error(raw_err)}

        resolved_user = str(auth_res.get("j_username") or student_id)

        # Step 4: Submit AuthnEngine to complete OAuth2 redirect back to OJ
        engine_url = (
            f"{IAM_BASE_URL}/idp/AuthnEngine?"
            f"currentAuth=urn_oasis_names_tc_SAML_2.0_ac_classes_BAMUsernamePassword"
            f"&authnLcKey={authn_lc_key}&entityId={IAM_ENTITY_ID}"
        )
        engine_payload = dict(form_payload, j_username=resolved_user)
        r3 = sess.post(
            engine_url,
            data=engine_payload,
            headers={
                "Referer": str(r1.url),
                "Origin": IAM_BASE_URL,
            },
            timeout=20,
            allow_redirects=True,
        )

        if not _is_oj_authenticated_response(r3):
            # Verify by requesting dashboard directly
            r_check = sess.get(OJ_DASHBOARD_URL, timeout=15, allow_redirects=True)
            if not _is_oj_authenticated_response(r_check):
                return {"ok": False, "error": "统一身份认证成功但未能建立实训平台会话，请确认已注册实训平台账号"}

        cookies = _session_cookies_dict(sess)
        save_credentials(username, student_id, password, login_mode="iam", cookies=cookies)
        _pending_iam_sessions.pop(username, None)
        return {"ok": True}
    except requests.RequestException as e:
        logger.warning(f"Tongji OJ IAM login network error for {username}: {e}")
        return {"ok": False, "error": f"网络连接失败: {e}"}
    except Exception as e:
        logger.warning(f"Tongji OJ IAM login unexpected error for {username}: {e}")
        return {"ok": False, "error": f"登录失败: {e}"}


def iam_send_second_auth_code(username: str, auth_type: str = "sms") -> dict:
    """Send SMS or email verification code for pending Tongji IAM enhanced authentication."""
    pending = _pending_iam_sessions.get(username)
    if not pending or (time.time() - pending.get("created_at", 0)) > 600:
        _pending_iam_sessions.pop(username, None)
        return {"ok": False, "error": "加强认证会话已过期，请重新点击「统一身份认证登录」"}

    sess: requests.Session = pending["session"]
    method = "email" if auth_type == "email" else "sms"
    try:
        resp = sess.post(
            f"{IAM_BASE_URL}/idp/sendCheckCode.do",
            data={
                "j_username": pending["show_username"],
                "type": method,
            },
            headers={
                "Accept": IAM_AJAX_ACCEPT,
                "Referer": pending["referer"],
                "Origin": IAM_BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        data = _parse_iam_ajax_response(resp) or {}
        msg_key = str(data.get("message") or "")
        if "sendSMSCheckCodeSuccessmsg" in msg_key:
            valid_time = str(data.get("validTime") or "3")
            return {"ok": True, "message": f"验证码已发送，有效期 {valid_time} 分钟"}
        if "sendSMSCheckCodeTooFast" in msg_key or "smsVerificationTime" in msg_key:
            return {"ok": False, "error": "获取验证码间隔过短（需间隔3分钟），请稍后再试或直接输入已收到的验证码"}
        return {"ok": False, "error": _clean_iam_error(msg_key or resp.text[:100], "发送验证码失败，请稍后重试")}
    except requests.RequestException as e:
        return {"ok": False, "error": f"发送验证码网络错误: {e}"}


def iam_verify_second_auth_code(username: str, code: str, auth_type: str = "sms") -> dict:
    """Complete Tongji IAM enhanced authentication with the SMS/email verification code."""
    pending = _pending_iam_sessions.get(username)
    if not pending or (time.time() - pending.get("created_at", 0)) > 600:
        _pending_iam_sessions.pop(username, None)
        return {"ok": False, "error": "加强认证会话已过期，请重新点击「统一身份认证登录」"}

    code = (code or "").strip()
    if not re.fullmatch(r"\d{4,8}", code):
        return {"ok": False, "error": "请输入收到的数字验证码"}

    sess: requests.Session = pending["session"]
    authn_lc_key = pending["authn_lc_key"]
    method = "email" if auth_type == "email" else "sms"
    form_4_payload = {
        "j_username": pending["show_username"],
        "type": method,
        "sms_checkcode": code,
        "popViewException": "Pop2",
        "op": "login",
        "spAuthChainCode": pending["sp_chain_code"],
        "j_checkcode": "请输入验证码",
    }
    try:
        action_url = f"{IAM_BASE_URL}/idp/authcenter/ActionAuthChain?authnLcKey={authn_lc_key}"
        r2 = sess.post(
            action_url,
            data=form_4_payload,
            headers={
                "Accept": IAM_AJAX_ACCEPT,
                "Referer": pending["referer"],
                "Origin": IAM_BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        auth_res = _parse_iam_ajax_response(r2)
        if not auth_res:
            return {"ok": False, "error": "加强认证响应格式异常，请重试"}

        login_failed = str(auth_res.get("loginFailed")).lower()
        view = str(auth_res.get("view") or "")
        if login_failed not in ("false", "none", "") and view != "none":
            raw_err = (
                auth_res.get("authnErrorTip")
                or auth_res.get("message")
                or auth_res.get("errorMsg")
                or "验证码错误或已过期，请重新输入"
            )
            return {"ok": False, "error": _clean_iam_error(raw_err, "验证码错误或已过期，请重新输入")}

        engine_4_url = (
            f"{IAM_BASE_URL}/idp/AuthnEngine?"
            f"currentAuth=urn_oasis_names_tc_SAML_2.0_ac_classes_SMSUsernamePassword"
            f"&authnLcKey={authn_lc_key}&entityId={IAM_ENTITY_ID}"
        )
        r3 = sess.post(
            engine_4_url,
            data=form_4_payload,
            headers={
                "Referer": pending["referer"],
                "Origin": IAM_BASE_URL,
            },
            timeout=20,
            allow_redirects=True,
        )
        if not _is_oj_authenticated_response(r3):
            r_check = sess.get(OJ_DASHBOARD_URL, timeout=15, allow_redirects=True)
            if not _is_oj_authenticated_response(r_check):
                return {"ok": False, "error": "加强认证通过但未能建立实训平台会话，请稍后重试"}

        cookies = _session_cookies_dict(sess)
        save_credentials(
            username,
            pending["student_id"],
            pending["password"],
            login_mode="iam",
            cookies=cookies,
        )
        _pending_iam_sessions.pop(username, None)
        return {"ok": True}
    except requests.RequestException as e:
        return {"ok": False, "error": f"网络连接失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"加强认证失败: {e}"}



def local_login(username: str, oj_account: str, password: str) -> dict:
    """Authenticate to oj.tongji.edu.cn via local U_Login form."""
    oj_account = (oj_account or "").strip()
    if not oj_account or not password:
        return {"ok": False, "error": "请输入实训平台用户名和密码"}

    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)

    try:
        r1 = sess.get(OJ_LOCAL_LOGIN_URL, timeout=15, allow_redirects=True)
        m_csrf = re.search(
            r'name=["\']shj_csrf_token["\'][^>]*value=["\']([^"\']+)["\']',
            r1.text,
        )
        csrf_token = m_csrf.group(1) if m_csrf else sess.cookies.get("shjcsrftoken", "")
        r2 = sess.post(
            OJ_LOCAL_LOGIN_URL,
            data={
                "shj_csrf_token": csrf_token,
                "username": oj_account,
                "password": password,
            },
            headers={"Referer": OJ_LOCAL_LOGIN_URL, "Origin": OJ_BASE_URL},
            timeout=15,
            allow_redirects=True,
        )
        if not _is_oj_authenticated_response(r2):
            return {"ok": False, "error": "实训平台用户名或密码错误"}

        cookies = _session_cookies_dict(sess)
        save_credentials(username, oj_account, password, login_mode="local", cookies=cookies)
        return {"ok": True}
    except requests.RequestException as e:
        logger.warning(f"Tongji OJ local login network error for {username}: {e}")
        return {"ok": False, "error": f"网络连接失败: {e}"}
    except Exception as e:
        logger.warning(f"Tongji OJ local login error for {username}: {e}")
        return {"ok": False, "error": f"登录失败: {e}"}


# ---- HTML Parsing (Read-Only List Pages) ----

class _TableTextParser(HTMLParser):
    """Lightweight HTML table parser that extracts rows of (text, hrefs) per cell.

    Works both with and without an explicit `<tbody>` tag (since raw Sharif-Judge
    PHP HTML omits `<tbody>` after `</thead>`).
    """

    def __init__(self):
        super().__init__()
        self.in_thead = False
        self.in_tr = False
        self.in_td = False
        self.rows: list[list[dict]] = []
        self._current_row: list[dict] = []
        self._current_text: list[str] = []
        self._current_hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "thead":
            self.in_thead = True
        elif tag == "tr" and not self.in_thead:
            self.in_tr = True
            self._current_row = []
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self._current_text = []
            self._current_hrefs = []
        elif tag == "a" and self.in_td:
            href = attrs_dict.get("href")
            if href:
                self._current_hrefs.append(href)

    def handle_endtag(self, tag):
        if tag == "thead":
            self.in_thead = False
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            if self._current_row:
                self.rows.append(self._current_row)
        elif tag == "td" and self.in_td:
            self.in_td = False
            text = re.sub(r"\s+", " ", "".join(self._current_text)).strip()
            self._current_row.append({"text": text, "hrefs": list(self._current_hrefs)})

    def handle_data(self, data):
        if self.in_td:
            self._current_text.append(data)


def _clean_course_name(raw_name: str, course_id: str = "") -> str:
    name = re.sub(r"\s+", " ", (raw_name or "")).strip()
    if course_id:
        name = re.sub(rf"^{re.escape(str(course_id))}\s*:\s*", "", name)
    name = re.sub(r"^\d+\s*:\s*", "", name)
    return name.strip()


def _parse_finish_time(raw_time: str) -> tuple[str, str | None, str | None]:
    """Parse OJ finish time 'YYYY-MM-DD HH:MM:SS' into (due_str, due_date, due_ts)."""
    text = (raw_time or "").strip()
    if not text or text.startswith("0000-00-00"):
        return "无截止时间", None, None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=CST)
            return (
                dt.strftime("%m-%d %H:%M"),
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                dt.isoformat(),
            )
        except ValueError:
            continue
    return text, None, None


def parse_assignments_html(html: str) -> tuple[list[dict], list[dict]]:
    """Parse `/index.php/assignments` HTML into `(courses, assignments)`.

    Does NOT make any network requests or open any assignment/problem links.
    Skips built-in pseudo-courses `0` (`My own assignments`) and `1` (`community`).
    """
    courses: list[dict] = []
    assignments: list[dict] = []

    # Match <h2 id="course_btn" data-id="{cid}" ...><a>{cname}</a>...</h2>
    # followed by <div id="course{cid}" ...>...<table class="sharif_table">...</table>
    heading_pattern = re.compile(
        r'<h2[^>]*\bdata-id=["\'](\d+)["\'][^>]*>.*?<a[^>]*>(.*?)</a>.*?</h2>',
        re.DOTALL | re.IGNORECASE,
    )

    for match in heading_pattern.finditer(html):
        course_id = match.group(1).strip()
        raw_course_title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if course_id in ("0", "1"):
            continue

        course_name = _clean_course_name(raw_course_title, course_id)
        if not course_name:
            continue
        courses.append({"id": course_id, "name": course_name})

        div_pattern = re.compile(
            rf'<div[^>]*\bid=["\']course{re.escape(course_id)}["\'][^>]*>(.*?)</table>',
            re.DOTALL | re.IGNORECASE,
        )
        div_match = div_pattern.search(html, match.end())
        if not div_match:
            continue

        parser = _TableTextParser()
        parser.feed(div_match.group(1) + "</table>")

        for row in parser.rows:
            if len(row) < 8:
                continue
            title = row[0]["text"]
            plan = row[1]["text"]
            prob_cell = row[2]
            submissions_text = row[3]["text"]
            coefficient = row[4]["text"]
            start_time = row[5]["text"]
            finish_time = row[6]["text"]
            status_text = row[7]["text"]

            if not title or "nothing to display" in title.lower():
                continue

            # Extract assignment_id from href (.../assignments/problems_list/3815) without visiting it
            assignment_id = None
            for href in prob_cell["hrefs"]:
                m_aid = re.search(r"/assignments/problems_list/(\d+)", href)
                if m_aid:
                    assignment_id = m_aid.group(1)
                    break
            if not assignment_id:
                assignment_id = f"{course_id}_{title}"

            m_pcount = re.search(r"(\d+)\s*problems?", prob_cell["text"], re.IGNORECASE)
            problem_count = int(m_pcount.group(1)) if m_pcount else 0

            assignments.append({
                "assignment_id": str(assignment_id),
                "course_id": str(course_id),
                "course": course_name,
                "title": title,
                "plan": plan,
                "problem_count": problem_count,
                "submissions_text": submissions_text,
                "coefficient": coefficient,
                "start_time": start_time,
                "finish_time": finish_time,
                "status": status_text,
            })

    return courses, assignments


def parse_final_submissions_html(html: str) -> dict:
    """Parse `/index.php/submissions/final/course/all` HTML.

    Returns:
      {
        "problem_counts_by_assignment": {(course_id, assignment_id): int},
        "submitted_problems_by_key": {(course_name, assignment_name): set[str]},
      }
    """
    problem_counts_by_assignment: dict[tuple[str, str], int] = {}
    submitted_problems_by_key: dict[tuple[str, str], set[str]] = {}

    # 1. Extract problem counts from inline search_data if available:
    # search_data['courses']['45']['assignments']['3815']['problems']['7452'] = {'id': ...}
    prob_assign_matches = re.findall(
        r"search_data\['courses'\]\['(\d+)'\]\['assignments'\]\['(\d+)'\]\['problems'\]\['(\d+)'\]\s*=",
        html,
    )
    problems_map: dict[tuple[str, str], set[str]] = {}
    for cid, aid, pid in prob_assign_matches:
        problems_map.setdefault((cid, aid), set()).add(pid)
    for key, pids in problems_map.items():
        problem_counts_by_assignment[key] = len(pids)

    # 2. Parse final submission rows from <table class="sharif_table">
    table_match = re.search(
        r'<table[^>]*class=["\'][^"\']*sharif_table[^"\']*["\'][^>]*>(.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if table_match:
        parser = _TableTextParser()
        parser.feed(table_match.group(0))
        for row in parser.rows:
            if len(row) < 3:
                continue
            first_cell = row[0]["text"]
            if "nothing to display" in first_cell.lower():
                continue
            course_name = _clean_course_name(first_cell)
            assignment_name = row[1]["text"].strip()
            problem_name = row[2]["text"].strip()
            if course_name and assignment_name and problem_name:
                submitted_problems_by_key.setdefault((course_name, assignment_name), set()).add(problem_name)

    return {
        "problem_counts_by_assignment": problem_counts_by_assignment,
        "submitted_problems_by_key": submitted_problems_by_key,
    }


def build_unfinished_todos(
    assignments: list[dict],
    submissions_info: dict,
    selected_course: str | None = None,
) -> list[dict]:
    """Filter parsed assignments against final submissions to produce unified todo items."""
    problem_counts_map = submissions_info.get("problem_counts_by_assignment", {})
    submitted_map = submissions_info.get("submitted_problems_by_key", {})

    todos: list[dict] = []
    for asg in assignments:
        course_id = str(asg.get("course_id") or "")
        if selected_course and course_id != str(selected_course):
            continue

        assignment_id = str(asg.get("assignment_id") or "")
        course_name = asg.get("course") or ""
        title = asg.get("title") or ""
        status_text = (asg.get("status") or "").strip().lower()

        # Only include open assignments
        if status_text and status_text != "open":
            continue

        problem_count = int(asg.get("problem_count") or 0)
        if (course_id, assignment_id) in problem_counts_map:
            problem_count = max(problem_count, problem_counts_map[(course_id, assignment_id)])

        if problem_count <= 0:
            continue

        submitted_problems = submitted_map.get((course_name, title), set())
        submitted_count = len(submitted_problems)

        # Completed when all problems in this assignment have a final submission
        if submitted_count >= problem_count:
            continue

        due_str, due_date, due_ts = _parse_finish_time(asg.get("finish_time") or "")

        todos.append({
            "id": f"tjoj_{assignment_id}",
            "assignment_id": assignment_id,
            "title": title,
            "course": course_name,
            "course_id": course_id,
            "due_str": due_str,
            "due_date": due_date or (asg.get("finish_time") or ""),
            "due_ts": due_ts,
            "type": "编程作业",
            "type_raw": "assignment",
            "problem_count": problem_count,
            "submitted_count": submitted_count,
            "url": OJ_ASSIGNMENTS_URL,
        })

    todos.sort(key=lambda t: (0 if t["due_ts"] else 1, t["due_ts"] or "9999-99-99"))
    return todos


# ---- Cache & Live Fetch ----

CACHE_SCHEMA_VERSION = 2


def _read_cache_payload(username: str) -> dict | None:
    cache_file = _cache_file(username)
    if not cache_file.exists():
        return None
    cached = read_json_file(cache_file, {})
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        return cached
    return None


def _is_cache_fresh(cached: dict | None) -> bool:
    if not cached or cached.get("version") != CACHE_SCHEMA_VERSION or not cached.get("updated_at"):
        return False
    try:
        updated_at = datetime.fromisoformat(cached["updated_at"])
        return (datetime.now(CST) - updated_at).total_seconds() < CACHE_TTL
    except Exception:
        return False


def _save_cache_payload(username: str, items: list[dict], courses: list[dict]):
    write_json_file(
        _cache_file(username),
        {
            "version": CACHE_SCHEMA_VERSION,
            "items": items,
            "courses": courses,
            "updated_at": datetime.now(CST).isoformat(),
        },
    )


def _fetch_authenticated_pages(username: str) -> tuple[str | None, str | None, str | None]:
    """Return `(assignments_html, submissions_html, error_message)` using stored session or re-login."""
    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)

    cookies = _load_cookies(username)
    if cookies:
        sess.cookies.update(cookies)

    def _try_get_pages():
        r_asg = sess.get(OJ_ASSIGNMENTS_URL, timeout=15, allow_redirects=True)
        if not _is_oj_authenticated_response(r_asg):
            return None, None
        r_sub = sess.get(OJ_FINAL_SUBMISSIONS_URL, timeout=15, allow_redirects=True)
        if not _is_oj_authenticated_response(r_sub):
            return None, None
        return r_asg.text, r_sub.text

    try:
        asg_html, sub_html = _try_get_pages()
        if asg_html is not None and sub_html is not None:
            _save_cookies(username, _session_cookies_dict(sess))
            return asg_html, sub_html, None
    except requests.RequestException as e:
        logger.warning(f"Tongji OJ initial fetch failed for {username}: {e}")
        return None, None, f"网络请求失败: {e}"

    # Session expired or missing -> try automatic re-login with stored credentials
    creds = load_credentials(username)
    if not creds:
        _cookie_cache.pop(username, None)
        return None, None, "会话已过期，请重新登录同济竞教实训平台"

    login_mode = creds.get("login_mode") or "iam"
    if login_mode == "local":
        login_res = local_login(username, creds["username"], creds["password"])
    else:
        login_res = iam_login(username, creds["username"], creds["password"])

    if not login_res.get("ok"):
        return None, None, login_res.get("error") or "自动重新登录失败，请重新配置账号"

    # Retry page fetch with fresh cookies
    fresh_cookies = _load_cookies(username) or {}
    sess.cookies.clear()
    sess.cookies.update(fresh_cookies)
    try:
        asg_html, sub_html = _try_get_pages()
        if asg_html is not None and sub_html is not None:
            return asg_html, sub_html, None
        return None, None, "登录后仍无法读取作业页面，请稍后重试"
    except requests.RequestException as e:
        return None, None, f"网络请求失败: {e}"


def fetch_courses(username: str) -> dict:
    """Return enrolled courses for `username`."""
    saved = get_saved_courses(username)
    if saved:
        return {"ok": True, "courses": saved}

    if not has_credentials(username):
        return {"ok": False, "error": "未配置同济OJ账号", "need_setup": True}

    asg_html, _, err = _fetch_authenticated_pages(username)
    if err or asg_html is None:
        return {"ok": False, "error": err or "获取课程失败"}

    courses, _ = parse_assignments_html(asg_html)
    _save_courses(username, courses)
    return {"ok": True, "courses": courses}


def fetch_assignments(
    username: str,
    course_id: str | None = None,
    force_fetch: bool = False,
) -> dict:
    """Fetch unfinished assignments for `username` from oj.tongji.edu.cn."""
    if not has_credentials(username):
        return {"ok": False, "error": "未配置同济OJ账号", "need_setup": True}

    selected = course_id if course_id is not None else get_selected_course(username)
    cached_payload = _read_cache_payload(username)

    if not force_fetch and not selected and _is_cache_fresh(cached_payload):
        return {"ok": True, "items": cached_payload["items"], "cached": True}

    asg_html, sub_html, err = _fetch_authenticated_pages(username)
    if err or asg_html is None or sub_html is None:
        if cached_payload is not None:
            items = cached_payload["items"]
            if selected:
                items = [it for it in items if str(it.get("course_id")) == str(selected)]
            return {"ok": True, "items": items, "cached": True, "stale": True}
        return {"ok": False, "error": err or "获取同济OJ作业失败"}

    courses, all_assignments = parse_assignments_html(asg_html)
    submissions_info = parse_final_submissions_html(sub_html)
    all_todos = build_unfinished_todos(all_assignments, submissions_info, selected_course=None)

    _save_courses(username, courses)
    _save_cache_payload(username, all_todos, courses)

    filtered_todos = (
        [it for it in all_todos if str(it.get("course_id")) == str(selected)]
        if selected
        else all_todos
    )
    return {"ok": True, "items": filtered_todos, "courses": courses, "cached": False}


# ---- Local State Management (hidden / highlighted / deleted / completed / overrides) ----

has_token = has_credentials

_STATE = PlatformStateStore(lambda username: user_dir(username) / "tongjioj_state.json", str)
load_state = _STATE.load
save_state = _STATE.save
update_state = _STATE.update
update_override = _STATE.update_override
