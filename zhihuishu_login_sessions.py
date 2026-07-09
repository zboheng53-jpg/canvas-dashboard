"""Short-lived per-user Zhihuishu browser login sessions."""
import json
import os
import re
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import settings
from storage import read_json_file, write_json_file

DATA_DIR = Path(__file__).parent / "data"

SESSION_TTL_SECONDS = settings.ZHIHUISHU_LOGIN_SESSION_TTL_SECONDS
PORT_START = settings.ZHIHUISHU_LOGIN_PORT_START
PORT_END = settings.ZHIHUISHU_LOGIN_PORT_END
DOCKER_IMAGE = settings.ZHIHUISHU_LOGIN_DOCKER_IMAGE
NOVNC_READY_TIMEOUT_SECONDS = settings.ZHIHUISHU_NOVNC_READY_TIMEOUT_SECONDS
NOVNC_READY_INTERVAL_SECONDS = settings.ZHIHUISHU_NOVNC_READY_INTERVAL_SECONDS
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _user_dir(username: str) -> Path:
    path = DATA_DIR / "users" / username
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_file(username: str) -> Path:
    return _user_dir(username) / "zhihuishu_login_session.json"


def _profile_dir(username: str) -> Path:
    path = _user_dir(username) / "zhihuishu_chromium_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _container_name(token: str) -> str:
    safe = "".join(ch for ch in token if ch.isalnum() or ch in ("-", "_"))
    return f"canvas-zhs-login-{safe[:24]}"


def _find_free_port() -> int:
    for port in range(PORT_START, PORT_END + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free Zhihuishu login ports available")


def _run_docker(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Docker 运行时没有准备好，无法启动智慧树登录窗口：没有找到 docker 命令。"
            "本地调试需要安装 Docker Desktop；服务器需要安装 Docker、构建 "
            f"{DOCKER_IMAGE}，并让运行 canvas-dashboard 的用户可以执行 docker。"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Docker 启动智慧树登录窗口失败。请确认 Docker 正在运行、登录浏览器镜像已构建，"
            "并且运行 canvas-dashboard 的用户有 docker 权限。"
        ) from exc


def _wait_for_novnc(port: int) -> None:
    url = f"http://127.0.0.1:{port}/vnc.html"
    deadline = time.monotonic() + NOVNC_READY_TIMEOUT_SECONDS
    last_error = None

    while True:
        try:
            timeout = max(0.1, min(1.0, deadline - time.monotonic()))
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                if resp.status == 200:
                    return
                last_error = RuntimeError(f"HTTP {resp.status}")
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(NOVNC_READY_INTERVAL_SECONDS, remaining))

    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(
        f"智慧树登录窗口启动超时：noVNC 在 127.0.0.1:{port} 没有准备好{detail}"
    )


def _stop_container(container_name: str) -> None:
    if not container_name:
        return
    try:
        subprocess.run(["docker", "rm", "-f", container_name], check=False)
    except FileNotFoundError:
        return


def _parse_allowed_port(port: int | str) -> int | None:
    try:
        parsed = int(port)
    except (TypeError, ValueError):
        return None
    if PORT_START <= parsed <= PORT_END:
        return parsed
    return None


def _valid_token(token: str) -> bool:
    return isinstance(token, str) and TOKEN_RE.fullmatch(token) is not None


def _iter_session_files():
    users_dir = DATA_DIR / "users"
    if not users_dir.exists():
        return
    for user_dir in users_dir.iterdir():
        if user_dir.is_dir():
            yield user_dir / "zhihuishu_login_session.json"


def _remove_session_file(session_file: Path, session: dict) -> None:
    _stop_container(session.get("container_name", ""))
    session_file.unlink(missing_ok=True)


def cleanup_expired_sessions(now: float | None = None) -> None:
    now = time.time() if now is None else now
    for session_file in _iter_session_files() or []:
        if not session_file.exists():
            continue
        try:
            session = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if float(session.get("expires_at", 0)) < now:
            _remove_session_file(session_file, session)


def build_docker_command(username: str, token: str, port: int) -> list[str]:
    profile = _profile_dir(username).resolve()
    command = [
        "docker", "run", "-d",
        "--rm",
        "--name", _container_name(token),
        "--label", "canvas-dashboard=zhihuishu-login",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "--cpus", "0.5",
        "--memory", "512m",
        "--pids-limit", "256",
        "--shm-size", "1g",
        "-p", f"127.0.0.1:{port}:6080",
        "-v", f"{profile}:/profile",
        "-e", "ZHIHUISHU_LOGIN_URL=https://passport.zhihuishu.com/login",
        DOCKER_IMAGE,
    ]
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        command[command.index("-p"):command.index("-p")] = ["--user", f"{os.getuid()}:{os.getgid()}"]
    return command


def load_session(username: str) -> dict | None:
    path = _session_file(username)
    if not path.exists():
        return None
    try:
        return read_json_file(path, None)
    except Exception:
        return None


def _save_session(username: str, session: dict) -> None:
    path = _session_file(username)
    write_json_file(path, session)


def create_session(username: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cleanup_expired_sessions(now)
    existing = load_session(username)
    if existing:
        _stop_container(existing.get("container_name", ""))

    token = secrets.token_urlsafe(32)
    port = _find_free_port()
    container_name = _container_name(token)
    command = build_docker_command(username, token, port)
    _run_docker(command)
    try:
        _wait_for_novnc(port)
    except Exception:
        _stop_container(container_name)
        raise

    session = {
        "username": username,
        "token": token,
        "port": port,
        "container_name": container_name,
        "created_at": now,
        "expires_at": now + SESSION_TTL_SECONDS,
        "url": f"/zhihuishu/session/{token}/",
    }
    _save_session(username, session)
    return session


def validate_session(token: str, port: int | str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    if not _valid_token(token):
        return False
    expected_port = _parse_allowed_port(port)
    if expected_port is None:
        return False

    users_dir = DATA_DIR / "users"
    if not users_dir.exists():
        return False

    for session_file in _iter_session_files() or []:
        if not session_file.exists():
            continue
        try:
            session = json.loads(session_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if float(session.get("expires_at", 0)) < now:
            _remove_session_file(session_file, session)
            continue
        if session.get("token") != token:
            continue
        session_port = _parse_allowed_port(session.get("port"))
        if session_port != expected_port:
            return False
        return True
    return False


def session_for_token(token: str) -> dict | None:
    if not _valid_token(token):
        return None
    cleanup_expired_sessions()
    users_dir = DATA_DIR / "users"
    if not users_dir.exists():
        return None
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        session = load_session(user_dir.name)
        if session and session.get("token") == token:
            return session
    return None


def stop_session(username: str, token: str | None = None) -> bool:
    session = load_session(username)
    if not session:
        return False
    if token is not None and session.get("token") != token:
        return False
    _stop_container(session.get("container_name", ""))
    _session_file(username).unlink(missing_ok=True)
    return True
