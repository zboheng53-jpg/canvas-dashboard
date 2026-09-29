"""Bound noVNC browser starts across both login providers in one WSGI process."""
from contextlib import contextmanager
import threading

import settings
from storage import read_json_file

_startup_lock = threading.Lock()
SESSION_FILES = ('tongji_login_session.json', 'zhihuishu_login_session.json')


class LoginCapacityError(RuntimeError):
    pass


@contextmanager
def startup_slot(data_dir, replacing):
    # Do not queue slow browser starts on the limited Waitress request pool.
    if not _startup_lock.acquire(blocking=False):
        raise LoginCapacityError('有同学正在启动认证窗口，请稍后再试。')
    try:
        active = 0
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
    finally:
        _startup_lock.release()
