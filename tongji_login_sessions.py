"""Short-lived noVNC sessions for Tongji enhanced authentication."""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import settings
from storage import read_json_file, write_json_file

DATA_DIR = Path(__file__).parent / "data"
SESSION_TTL_SECONDS = settings.TONGJI_LOGIN_SESSION_TTL_SECONDS
PORT_START = settings.TONGJI_LOGIN_PORT_START
PORT_END = settings.TONGJI_LOGIN_PORT_END
DEBUG_PORT_START = settings.TONGJI_LOGIN_DEBUG_PORT_START
DEBUG_PORT_END = settings.TONGJI_LOGIN_DEBUG_PORT_END
DOCKER_IMAGE = settings.TONGJI_LOGIN_DOCKER_IMAGE
NOVNC_READY_TIMEOUT_SECONDS = settings.TONGJI_NOVNC_READY_TIMEOUT_SECONDS
NOVNC_READY_INTERVAL_SECONDS = settings.TONGJI_NOVNC_READY_INTERVAL_SECONDS
LOGIN_URL = "https://1.tongji.edu.cn/GraduateStudentTimeTable"
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _user_dir(username: str) -> Path:
    path = DATA_DIR / "users" / username
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_file(username: str) -> Path:
    return _user_dir(username) / "tongji_login_session.json"


def _profile_dir(username: str) -> Path:
    path = _user_dir(username) / "tongji_login_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _container_name(token: str) -> str:
    return f"canvas-tongji-login-{token[:24]}"


def _find_free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("没有可用的同济认证窗口端口")


def _run_docker(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Docker 未准备好，无法启动同济认证窗口") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("同济认证窗口启动失败，请确认 Docker 正在运行且浏览器镜像已构建") from exc


def _wait_for_novnc(port: int) -> None:
    deadline = time.monotonic() + NOVNC_READY_TIMEOUT_SECONDS
    last_error = None
    while True:
        try:
            timeout = max(0.1, min(1.0, deadline - time.monotonic()))
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/vnc.html", timeout=timeout) as response:
                if response.status == 200:
                    return
                last_error = RuntimeError(f"HTTP {response.status}")
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(NOVNC_READY_INTERVAL_SECONDS, remaining))
    detail = f"：{last_error}" if last_error else ""
    raise RuntimeError(f"同济认证窗口启动超时{detail}")


def _stop_container(container_name: str) -> None:
    if not container_name:
        return
    try:
        subprocess.run(["docker", "rm", "-f", container_name], check=False)
    except FileNotFoundError:
        pass


def _remove_profile(username: str) -> None:
    profile = _profile_dir(username)
    if profile.exists():
        shutil.rmtree(profile)


def _iter_session_files():
    users_dir = DATA_DIR / "users"
    if users_dir.exists():
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir():
                yield user_dir / "tongji_login_session.json"


def _remove_session_file(session_file: Path, login_session: dict) -> None:
    _stop_container(login_session.get("container_name", ""))
    _remove_profile(login_session.get("username", ""))
    session_file.unlink(missing_ok=True)


def cleanup_expired_sessions(now: float | None = None) -> int:
    now = time.time() if now is None else now
    removed = 0
    for session_file in _iter_session_files():
        try:
            login_session = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if float(login_session.get("expires_at", 0)) < now:
            _remove_session_file(session_file, login_session)
            removed += 1
    return removed


def _list_login_containers() -> list[str]:
    command = ["docker", "ps", "-a", "--filter", "label=canvas-dashboard=tongji-login", "--format", "{{.Names}}"]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def cleanup_orphaned_containers(now: float | None = None) -> int:
    now = time.time() if now is None else now
    active = set()
    for session_file in _iter_session_files():
        try:
            login_session = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if float(login_session.get("expires_at", 0)) >= now:
            active.add(login_session.get("container_name", ""))
    orphans = [name for name in _list_login_containers() if name not in active]
    for name in orphans:
        _stop_container(name)
    return len(orphans)


def cleanup_login_lifecycle(now: float | None = None) -> dict:
    return {
        "expired_sessions": cleanup_expired_sessions(now),
        "orphaned_containers": cleanup_orphaned_containers(now),
    }


def build_docker_command(username: str, token: str, port: int, debug_port: int) -> list[str]:
    profile = _profile_dir(username).resolve()
    command = [
        "docker", "run", "-d", "--rm", "--name", _container_name(token),
        "--label", "canvas-dashboard=tongji-login", "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL", "--cpus", "0.5", "--memory", "512m", "--pids-limit", "256",
        "--shm-size", "1g", "-p", f"127.0.0.1:{port}:6080", "-p", f"127.0.0.1:{debug_port}:9223",
        "-v", f"{profile}:/profile", "-e", f"LOGIN_URL={LOGIN_URL}",
        "-e", "CHROME_REMOTE_DEBUGGING_PORT=9222",
        "-e", "CHROME_REMOTE_DEBUGGING_PROXY_PORT=9223", DOCKER_IMAGE,
    ]
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        command[command.index("-p"):command.index("-p")] = ["--user", f"{os.getuid()}:{os.getgid()}"]
    return command


def load_session(username: str) -> dict | None:
    try:
        return read_json_file(_session_file(username), None)
    except Exception:
        return None


def create_session(username: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cleanup_expired_sessions(now)
    stop_session(username)
    token = secrets.token_urlsafe(32)
    port = _find_free_port(PORT_START, PORT_END)
    debug_port = _find_free_port(DEBUG_PORT_START, DEBUG_PORT_END)
    command = build_docker_command(username, token, port, debug_port)
    _run_docker(command)
    try:
        _wait_for_novnc(port)
    except Exception:
        _stop_container(_container_name(token))
        _remove_profile(username)
        raise
    login_session = {
        "username": username, "token": token, "port": port, "debug_port": debug_port,
        "container_name": _container_name(token), "created_at": now,
        "expires_at": now + SESSION_TTL_SECONDS, "url": f"/schedule/session/{token}/",
    }
    write_json_file(_session_file(username), login_session)
    return login_session


def _valid_token(token: str) -> bool:
    return isinstance(token, str) and TOKEN_RE.fullmatch(token) is not None


def session_for_token(token: str) -> dict | None:
    if not _valid_token(token):
        return None
    cleanup_expired_sessions()
    for session_file in _iter_session_files():
        try:
            login_session = read_json_file(session_file, None)
        except Exception:
            continue
        if login_session and login_session.get("token") == token:
            return login_session
    return None


def validate_session(token: str, port: int | str, now: float | None = None) -> bool:
    if not _valid_token(token):
        return False
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if not PORT_START <= port <= PORT_END:
        return False
    login_session = session_for_token(token)
    return bool(login_session and login_session.get("port") == port)


def stop_session(username: str, token: str | None = None) -> bool:
    login_session = load_session(username)
    if not login_session or (token is not None and login_session.get("token") != token):
        return False
    _remove_session_file(_session_file(username), login_session)
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage Tongji noVNC login sessions.")
    parser.add_argument("--cleanup-expired", action="store_true")
    if parser.parse_args().cleanup_expired:
        print(json.dumps(cleanup_login_lifecycle(), ensure_ascii=False))
