"""Shared HTTP validation, errors and Agent authentication."""
import auth
import agent_auth
import settings
from datetime import timedelta, timezone
from flask import jsonify, request
from functools import wraps


def _get_external_base_url() -> str:
    """Derive external-facing base URL taking reverse proxy headers and settings into account."""
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL
    # ProxyFix applies only the approved protocol header. Forwarded Host/Prefix
    # never participate in externally visible credential URLs.
    return request.host_url.rstrip("/")


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


def require_agent_auth(scope_or_func=None):
    """Enforce Bearer authentication and optional scope permissions (read, write, delete)."""
    def make_decorator(required_scope=None):
        def decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                auth_header = request.headers.get("Authorization", "").strip()
                if not auth_header.startswith("Bearer "):
                    return api_error("unauthorized", "缺少或无效的 Authorization Bearer 凭据", 401)
                token = auth_header[7:].strip()
                token_ctx = agent_auth.resolve_token(token)
                if not token_ctx:
                    return api_error("unauthorized", "Agent API Token 无效、已过期或已撤销", 401)

                username = token_ctx["username"]
                from flask import current_app
                limit = current_app.config.get('AGENT_RATE_LIMITER')
                if limit:
                    allowed, retry_after = limit('agent-token', token_ctx['token_hash_prefix'], settings.AGENT_RATE_LIMIT_ATTEMPTS, settings.AGENT_RATE_LIMIT_SECONDS)
                    if not allowed:
                        response, status = api_error('rate_limited', 'Agent 调用过于频繁，请稍后重试', 429)
                        response.headers['Retry-After'] = str(retry_after)
                        return response, status
                with auth.account_operation(username):
                    token_ctx = agent_auth.resolve_token(token)
                    if not token_ctx or token_ctx["username"] != username:
                        return api_error("unauthorized", "Agent Token 已失效", 401)
                    scopes = set(token_ctx.get("scopes", ["read"]))
                    request.agent_username = username
                    request.agent_scopes = scopes
                    request.agent_token_id = token_ctx.get("token_id")

                    req_scope = required_scope
                    if not req_scope:
                        if request.method in ("GET", "HEAD", "OPTIONS"):
                            req_scope = "read"
                        elif request.method == "DELETE":
                            req_scope = "delete"
                        else:
                            req_scope = "write"

                    if req_scope not in scopes:
                        scope_desc = {
                            "read": "只读 (read)",
                            "write": "写入 (write)",
                            "delete": "删除 (delete)",
                        }.get(req_scope, req_scope)
                        return api_error(
                            "insufficient_scope",
                            f"当前 Agent Token 缺少 {scope_desc} 权限，请在网页生成具有相应权限的 Token",
                            403,
                            required_scope=req_scope,
                            current_scopes=list(scopes),
                        )

                    return f(*args, **kwargs)
            return decorated
        return decorator

    if callable(scope_or_func):
        return make_decorator(None)(scope_or_func)
    return make_decorator(scope_or_func)
