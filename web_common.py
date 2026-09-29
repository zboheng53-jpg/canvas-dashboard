"""Shared HTTP validation, errors and Agent authentication."""
import agent_auth
from datetime import timedelta, timezone
from flask import jsonify, request
from functools import wraps


def _get_external_base_url() -> str:
    """Derive external-facing base URL taking reverse proxy headers into account."""
    proto = request.headers.get("X-Forwarded-Proto", "").strip().lower()
    host = request.headers.get("X-Forwarded-Host", "").strip() or request.headers.get("Host", "").strip()
    if proto and host:
        return f"{proto}://{host}".rstrip("/")
    url = request.host_url.rstrip("/")
    if proto == "https" and url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


CST = timezone(timedelta(hours=8))


def read_json_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def invalid_request_response():
    return jsonify({"ok": False, "error": "无效请求"}), 400


def api_error(code, message, status=400, **extra):
    payload = {"ok": False, "code": code, "error": message}
    payload.update(extra)
    return jsonify(payload), status


def _with_default_error_code(result, code):
    if result.get("ok") is False and "code" not in result:
        result = dict(result)
        result["code"] = code
    return result


def require_agent_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "").strip()
        if not auth_header.startswith("Bearer "):
            return api_error("unauthorized", "缺少或无效的 Authorization Bearer 凭据", 401)
        token = auth_header[7:].strip()
        username = agent_auth.username_for_token(token)
        if not username:
            return api_error("unauthorized", "Agent API Token 无效或已撤销", 401)
        request.agent_username = username
        return f(*args, **kwargs)
    return decorated

