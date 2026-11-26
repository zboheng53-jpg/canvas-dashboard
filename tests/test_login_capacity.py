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


def test_login_container_caps_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setattr(zhihuishu_login_sessions, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(tongji_login_sessions, 'DATA_DIR', tmp_path)

    zhs_cmd = zhihuishu_login_sessions.build_docker_command('alice', 'tok_123456789012', 6107)
    tji_cmd = tongji_login_sessions.build_docker_command('alice', 'tok_123456789012', 6207, 6307)
    for cmd in (zhs_cmd, tji_cmd):
        assert cmd[cmd.index('--memory') + 1] == '768m'
        assert cmd[cmd.index('--cpus') + 1] == '0.75'
        assert cmd[cmd.index('--pids-limit') + 1] == '384'

    monkeypatch.setattr(settings, 'LOGIN_CONTAINER_MEMORY', '1g')
    monkeypatch.setattr(settings, 'LOGIN_CONTAINER_CPUS', '1.0')
    monkeypatch.setattr(settings, 'LOGIN_CONTAINER_PIDS_LIMIT', '512')

    zhs_override = zhihuishu_login_sessions.build_docker_command('alice', 'tok_123456789012', 6107)
    tji_override = tongji_login_sessions.build_docker_command('alice', 'tok_123456789012', 6207, 6307)
    for cmd in (zhs_override, tji_override):
        assert cmd[cmd.index('--memory') + 1] == '1g'
        assert cmd[cmd.index('--cpus') + 1] == '1.0'
        assert cmd[cmd.index('--pids-limit') + 1] == '512'


def test_two_worker_slots_leave_one_interactive_login_slot_under_default_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOGIN_MAX_SESSIONS', 3)
    with login_capacity.worker_browser_slot(tmp_path, 'alice'):
        with login_capacity.worker_browser_slot(tmp_path, 'bobby'):
            with login_capacity.startup_slot(tmp_path, tmp_path / 'users/carol/zhihuishu_login_session.json'):
                assert login_capacity.capacity_snapshot(tmp_path)['worker_browsers'] == 2


def test_zhihuishu_login_session_complete_current_lifecycle(isolated_data, monkeypatch):
    import time
    import app
    import zhihuishu_store
    import zhihuishu_worker

    monkeypatch.setitem(app.app.config, 'TESTING', True)
    auth.register('alice', 'password1')

    anon = app.app.test_client()
    assert anon.post('/api/zhihuishu/login-session/complete').status_code == 401

    client = operation_client(app.app)
    with client.session_transaction() as sess:
        sess.update(username='alice', _csrf_token='test')
    headers = {'X-CSRF-Token': 'test'}

    # Missing session -> 404
    monkeypatch.setattr(app.zhihuishu_login_sessions, 'load_session', lambda username: None)
    missing = client.post('/api/zhihuishu/login-session/complete', headers=headers)
    assert missing.status_code == 404

    # Expired session -> 404
    monkeypatch.setattr(
        app.zhihuishu_login_sessions,
        'load_session',
        lambda username: {'username': username, 'token': 'tok_expired_123456', 'expires_at': time.time() - 10},
    )
    expired = client.post('/api/zhihuishu/login-session/complete', headers=headers)
    assert expired.status_code == 404

    # Active session but login not detected -> 400
    stopped = []
    monkeypatch.setattr(
        app.zhihuishu_login_sessions,
        'load_session',
        lambda username: {'username': username, 'token': 'tok_active_1234567', 'expires_at': time.time() + 600},
    )
    monkeypatch.setattr(
        app.zhihuishu_login_sessions,
        'stop_session',
        lambda username, token=None: stopped.append((username, token)) or True,
    )
    monkeypatch.setattr(zhihuishu_worker, 'run_scheduled_cycle', lambda username, force_fetch=False: False)
    not_ready = client.post('/api/zhihuishu/login-session/complete', headers=headers)
    assert not_ready.status_code == 400
    assert stopped == [('alice', 'tok_active_1234567')]

    # Active session + detected login -> 200 and updates status
    stopped.clear()
    refreshed = []

    def ok_cycle(username, force_fetch=False):
        refreshed.append((username, force_fetch))
        zhihuishu_store.save_status(username, {'session': 'active', 'last_error': ''})
        return True

    monkeypatch.setattr(zhihuishu_worker, 'run_scheduled_cycle', ok_cycle)
    raw = client.post('/api/zhihuishu/login-session/complete', headers=headers)
    assert raw.status_code == 200
    assert raw.json['ok'] is True
    assert raw.json['status']['session'] == 'active'
    assert stopped == [('alice', 'tok_active_1234567')]
    assert refreshed == [('alice', True)]

    # Verify token-based route remains intact
    monkeypatch.setattr(
        app.zhihuishu_login_sessions,
        'session_for_token',
        lambda token: {'username': 'alice', 'token': token, 'expires_at': time.time() + 600},
    )
    legacy = client.post('/api/zhihuishu/login-session/tok_active_1234567/complete', headers=headers)
    assert legacy.status_code == 200
    assert legacy.json['ok'] is True
