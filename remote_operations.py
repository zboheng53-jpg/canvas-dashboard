"""Short submission/status requests for explicitly requested upstream operations."""
from functools import wraps
import secrets
import threading
import time

from flask import copy_current_request_context, current_app, jsonify, session, request

import auth
import http_sync

_lock = threading.Lock()
_tasks = {}
TASK_TTL_SECONDS = 600
MAX_TASKS = 64


def background_operation(platform, job_type):
    def decorate(view):
        @wraps(view)
        def submit(*args, **kwargs):
            if request.content_length and request.content_length > 16384:
                return jsonify({"ok": False, "error": "认证请求体过大"}), 413
            # Waitress closes its input after the 202 response. Cache the small
            # body before copying the request for a potentially queued worker.
            if len(request.get_data(cache=True)) > 16384:
                return jsonify({"ok": False, "error": "认证请求体过大"}), 413
            username = session["username"]
            identity = auth.session_identity(username)
            if identity is None:
                return jsonify({"ok": False, "code": "account_inactive", "error": "请重新登录"}), 401
            token = secrets.token_urlsafe(24)
            now = time.monotonic()
            with _lock:
                for key in list(_tasks):
                    if _tasks[key]["state"] == "done" and now - _tasks[key]["updated"] > TASK_TTL_SECONDS:
                        _tasks.pop(key)
                if len(_tasks) >= MAX_TASKS:
                    completed = [key for key in _tasks if _tasks[key]["state"] == "done"]
                    if completed:
                        _tasks.pop(completed[0])
                    else:
                        return jsonify({"ok": False, "code": "sync_capacity", "error": "后台任务已满，请稍后重试"}), 429, {"Retry-After": "30"}
                task = {"username": username, "identity": identity, "state": "queued", "updated": now}
                _tasks[token] = task
            app = current_app._get_current_object()

            @copy_current_request_context
            def run():
                with _lock:
                    task["state"] = "running"
                with auth.identity_scope(username, identity):
                    try:
                        response = app.make_response(view(*args, **kwargs))
                        result = response.get_json() or {"ok": False, "error": "后台操作返回无效结果"}
                        status = response.status_code
                        headers = {key: response.headers[key] for key in ("Retry-After",) if key in response.headers}
                    except auth.AccountIdentityChanged:
                        headers = {}
                        result, status = {"ok": False, "code": "account_changed", "error": "账户已变更，操作已取消"}, 409
                    except Exception as exc:
                        headers = {}
                        # Keep the task inspectable and never put exception text in logs/results.
                        from runtime_metrics import event
                        event("operation_error", platform=platform, error_type=type(exc).__name__)
                        result, status = {"ok": False, "error": "后台操作失败，请稍后重试"}, 502
                with _lock:
                    task.update(state="done", result=result, result_status=status, result_headers=headers, updated=time.monotonic())
                return result

            def finished():
                with _lock:
                    if task["state"] != "done":
                        task.update(state="done", result={"ok": False, "error": "任务已取消"},
                                    result_status=409, updated=time.monotonic())
            accepted = http_sync.submit_http_sync(username, platform, run, job_type=job_type, on_finished=finished)
            if not accepted:
                with _lock:
                    _tasks.pop(token, None)
                return jsonify({"ok": False, "code": "sync_capacity", "error": "已有同类操作或队列已满，请稍后重试"}), 429, {"Retry-After": "30"}
            return jsonify({"ok": True, "async_task": True, "state": "queued",
                            "status_url": "/api/operations/" + token}), 202
        return submit
    return decorate


def task_status(token, username):
    with _lock:
        task = _tasks.get(token)
        if not task or task["username"] != username or task["identity"] != auth.session_identity(username):
            return {"ok": False, "error": "任务不存在或已过期"}, 404
        if task["state"] != "done" and not http_sync.is_any_refreshing(username):
            task.update(state="done", result={"ok": False, "error": "任务已取消"}, result_status=409)
        return {key: task[key] for key in ("state", "result", "result_status", "result_headers") if key in task} | {"ok": True}, 200
