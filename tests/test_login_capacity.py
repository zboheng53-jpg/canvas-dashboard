import auth
from operation_helpers import operation_client
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

import login_capacity
import settings
import tongji_login_sessions
import zhihuishu_login_sessions
from storage import write_json_file


def test_shared_browser_limit_preserves_other_users_session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOGIN_MAX_SESSIONS', 1)
    existing = tmp_path / 'users/alice/zhihuishu_login_session.json'
    write_json_file(existing, {'token': 'test-only', 'expires_at': 99999})
    monkeypatch.setattr(tongji_login_sessions, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(tongji_login_sessions, '_run_docker', lambda _: pytest.fail('must not launch over capacity'))
    with pytest.raises(login_capacity.LoginCapacityError):
        tongji_login_sessions.create_session('bob', now=100)
    assert existing.exists()
    # Replacing a user's own browser does not consume another slot.
    with login_capacity.startup_slot(tmp_path, existing):
        pass


def test_parallel_login_starts_fail_fast_and_release_after_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOGIN_MAX_SESSIONS', 2)
    started, release = threading.Event(), threading.Event()
    def first():
        with login_capacity.startup_slot(tmp_path, tmp_path / 'first'):
            started.set()
            assert release.wait(5)
            raise RuntimeError('browser failed')
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(first)
        assert started.wait(5)
        try:
            with pytest.raises(login_capacity.LoginCapacityError):
                with login_capacity.startup_slot(tmp_path, tmp_path / 'second'):
                    pytest.fail('concurrent starts must not race port allocation')
        finally:
            release.set()
        with pytest.raises(RuntimeError):
            future.result()
    with login_capacity.startup_slot(tmp_path, tmp_path / 'third'):
        pass


def test_browser_capacity_returns_retryable_response(isolated_data, monkeypatch):
    import app
    monkeypatch.setitem(app.app.config, 'TESTING', True)
    def full(*_):
        raise login_capacity.LoginCapacityError('认证窗口暂时已满')
    monkeypatch.setattr(tongji_login_sessions, 'create_session', full)
    monkeypatch.setattr(zhihuishu_login_sessions, 'create_session', full)
    auth.register("alice", "password1")
    client = operation_client(app.app)
    with client.session_transaction() as session:
        session.update(username='alice', _csrf_token='test')
    for path in ('/api/schedule/login-session', '/api/zhihuishu/login-session'):
        response = client.post(path, headers={'X-CSRF-Token': 'test'})
        assert response.status_code == 429
        assert response.headers['Retry-After'] == '30'
        assert response.json['code'] == 'login_capacity'
