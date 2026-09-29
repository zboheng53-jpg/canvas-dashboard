"""Bound noVNC browser starts and background worker across the entire site."""
from contextlib import contextmanager
import os
import subprocess
import threading
import time
from pathlib import Path

import settings
from storage import interprocess_lock, read_json_file, write_json_file

_startup_lock = threading.RLock()
_profiles_guard = threading.Lock()
_profiles = {}
SESSION_FILES = ('tongji_login_session.json', 'zhihuishu_login_session.json')
WORKER_LEASE_FILE = '.worker_browser_lease.json'


def capacity_snapshot(data_dir):
    """Read resource records without removing leases or launching Docker."""
    sessions = 0
    starting = 0
    for filename in SESSION_FILES:
        for path in (data_dir / 'users').glob(f'*/{filename}'):
            record = read_json_file(path, None)
            if record:
                sessions += 1
                starting += record.get('status') == 'starting'
    records = read_json_file(data_dir / WORKER_LEASE_FILE, {})
    leases = records.get('leases', {}) if 'leases' in records else ({'legacy': records} if records else {})
    workers = sum(_lease_alive(lease) for lease in leases.values())
    return {'active_sessions': sessions, 'starting_sessions': starting, 'worker_browsers': workers,
            'occupied_slots': sessions + workers, 'max_sessions': settings.LOGIN_MAX_SESSIONS}


class LoginCapacityError(RuntimeError):
    pass


def stop_container(container_name):
    """Retain capacity/profile metadata until Docker confirms resource removal."""
    if not container_name:
        return
    try:
        result = subprocess.run(['docker', 'rm', '-f', container_name], check=False,
                                capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('认证容器停止失败，保留资源记录等待重试') from exc
    if result.returncode != 0 and 'no such container' not in (result.stderr or '').lower():
        raise RuntimeError('认证容器停止失败，保留资源记录等待重试')


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Access denied/unknown: keep the lease.
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _active_worker_leases(data_dir: Path) -> int:
    lease_path = data_dir / WORKER_LEASE_FILE
    if not lease_path.exists():
        return 0
    return len(_leases(data_dir))


def _lease_alive(lease):
    if _pid_is_running(int(lease.get('pid', 0))):
        return True
    # A dead leader does not prove its Chromium children have exited.
    if os.name != 'nt' and lease.get('pgid'):
        try:
            os.killpg(int(lease['pgid']), 0)
            return True
        except ProcessLookupError:
            pass
        except PermissionError:
            return True
    return False


def _leases(data_dir):
    path = data_dir / WORKER_LEASE_FILE
    data = read_json_file(path, {})
    if not isinstance(data, dict):
        raise LoginCapacityError('浏览器资源记录异常，等待维护。')
    records = data.get('leases', {}) if 'leases' in data else ({'legacy': data} if data else {})
    if not isinstance(records, dict) or any(not isinstance(v, dict) for v in records.values()):
        raise LoginCapacityError('浏览器资源记录异常，等待维护。')
    alive = {key: value for key, value in records.items() if _lease_alive(value)}
    if alive != records:
        write_json_file(path, {'leases': alive})
    return alive


@contextmanager
def _capacity_lock(data_dir, timeout=0.1):
    if not _startup_lock.acquire(blocking=False):
        raise LoginCapacityError('有认证窗口正在启动，请稍后再试。')
    try:
        try:
            with interprocess_lock(data_dir / 'browser_capacity', timeout=timeout):
                yield
        except TimeoutError as exc:
            raise LoginCapacityError('浏览器资源正在分配，请稍后再试。') from exc
    finally:
        _startup_lock.release()


@contextmanager
def startup_slot(data_dir, replacing):
    # Do not queue slow browser starts on the limited Waitress request pool.
    with _capacity_lock(data_dir):
        active = _active_worker_leases(data_dir)
        for filename in SESSION_FILES:
            for path in (data_dir / 'users').glob(f'*/{filename}'):
                if path == replacing:
                    continue
                # Count expired metadata until cleanup has actually stopped its
                # container. Corruption must not silently open another slot.
                if read_json_file(path, None):
                    active += 1
        if active >= settings.LOGIN_MAX_SESSIONS:
            raise LoginCapacityError('认证窗口暂时已满，请等其他同学完成登录后再试。已有待办仍可正常使用。')
        yield


@contextmanager
def worker_browser_slot(data_dir: Path, username: str = ""):
    """Acquire a global browser quota slot for background worker runs."""
    import secrets
    token = secrets.token_hex(16)
    lease_path = data_dir / WORKER_LEASE_FILE
    with _capacity_lock(data_dir):
        leases = _leases(data_dir)
        active = len(leases)
        for filename in SESSION_FILES:
            for path in (data_dir / 'users').glob(f'*/{filename}'):
                if read_json_file(path, None):
                    active += 1
        if active >= settings.LOGIN_MAX_SESSIONS:
            raise LoginCapacityError('全站浏览器配额已满，后台任务等待下轮')
        leases[token] = {
            'pid': os.getpid(), 'pgid': os.getpgrp() if os.name != 'nt' else None,
            'started_at': time.time(), 'username': username,
        }
        write_json_file(lease_path, {'leases': leases})
    try:
        yield
    finally:
        with _startup_lock, interprocess_lock(data_dir / 'browser_capacity'):
            leases = _leases(data_dir)
            leases.pop(token, None)
            write_json_file(lease_path, {'leases': leases})


@contextmanager
def account_profile_lock(data_dir: Path, username: str, timeout: float = 30.0, for_worker=False):
    """Acquire an exclusive cross-process lock for a user's browser profile."""
    target = data_dir / '.profile_locks' / username
    with _profiles_guard:
        lock = _profiles.setdefault(str(target.resolve()), threading.RLock())
    if not lock.acquire(timeout=timeout):
        raise TimeoutError('Profile is busy')
    try:
        with interprocess_lock(target, timeout=timeout):
            if for_worker and read_json_file(data_dir / 'users' / username / 'zhihuishu_login_session.json', None):
                raise LoginCapacityError('当前账户正在登录，后台抓取等待下轮')
            yield
    finally:
        lock.release()
