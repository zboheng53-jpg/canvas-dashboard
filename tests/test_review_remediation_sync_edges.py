from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
import subprocess
import sys
import threading

import pytest

import auth
import canvas_auth
import haoke_client
import http_sync
import login_capacity
import settings
import zhihuishu_browser
import zhihuishu_store
import zhihuishu_worker
import zhihuishu_login_sessions
import tongji_login_sessions
from storage import read_json_file, write_json_file


def test_http_queue_rejects_unknown_accounts_and_is_bounded(isolated_data, monkeypatch):
    assert not http_sync.submit_http_sync('missing', 'canvas', lambda: pytest.fail('unknown account'))
    for username in ('alice', 'bobby', 'carol'):
        auth.register(username, 'password1')
    monkeypatch.setattr(http_sync, 'HTTP_SYNC_MAX_JOBS', 2)
    started = threading.Barrier(3)
    release = threading.Event()
    def blocked():
        started.wait(timeout=5)
        assert release.wait(5)
    try:
        assert http_sync.submit_http_sync('alice', 'canvas', blocked)
        assert http_sync.submit_http_sync('bobby', 'haoke', blocked)
        started.wait(timeout=5)
        assert not http_sync.submit_http_sync('carol', 'canvas', lambda: pytest.fail('queue full'))
    finally:
        release.set()
        # Await the jobs without sleeping or peeking at executor internals.
        http_sync._executor.submit(lambda: None).result(timeout=5)
        http_sync._executor.submit(lambda: None).result(timeout=5)


@pytest.mark.parametrize('platform', ['canvas', 'haoke'])
def test_old_sync_does_not_publish_after_disconnect_and_reconnect(isolated_data, monkeypatch, platform):
    auth.register('alice', 'password1')
    cache = isolated_data / f'users/alice/{platform}_cache.json'
    old = [{'id': 'trusted', 'title': 'old'}]
    write_json_file(cache, old)
    called = []
    if platform == 'canvas':
        monkeypatch.setattr(canvas_auth, 'validate_feed_url', lambda _: (True, None))
        canvas_auth.save_feed_url('alice', 'https://canvas.tongji.edu.cn/feed.ics')
        class Response:
            status_code = 200
            text = 'calendar'
        def fetch(*args, **kwargs):
            called.append(True)
            canvas_auth.remove_feed_url('alice')
            canvas_auth.save_feed_url('alice', 'https://canvas.tongji.edu.cn/feed.ics')
            return Response()
        monkeypatch.setattr(canvas_auth.requests, 'get', fetch)
        monkeypatch.setattr(canvas_auth, '_parse_ical', lambda _: [{'id': 'canvas:assignment:42'}])
        canvas_auth._run_background_refresh('alice')
    else:
        haoke_client.save_credentials('alice', 'platformuser', 'password1')
        def fetch(username, publish=True):
            assert publish is False
            called.append(True)
            haoke_client.clear_credentials(username)
            haoke_client.save_credentials(username, 'platformuser', 'password1')
            return {'ok': True, 'data': [{'id': 42}], 'cached': False}
        monkeypatch.setattr(haoke_client, 'fetch_haoke_todos', fetch)
        haoke_client._run_background_refresh('alice')
    assert called == [True]
    assert read_json_file(cache, []) == old


def test_browser_workers_use_distinct_leases_and_old_live_lease_never_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOGIN_MAX_SESSIONS', 2)
    with login_capacity.worker_browser_slot(tmp_path, 'alice'):
        with login_capacity.worker_browser_slot(tmp_path, 'bobby'):
            assert login_capacity._active_worker_leases(tmp_path) == 2
            with pytest.raises(login_capacity.LoginCapacityError):
                with login_capacity.worker_browser_slot(tmp_path, 'carol'):
                    pytest.fail('over capacity')
        assert login_capacity._active_worker_leases(tmp_path) == 1
    assert login_capacity._active_worker_leases(tmp_path) == 0
    write_json_file(tmp_path / login_capacity.WORKER_LEASE_FILE, {'pid': os.getpid(), 'started_at': 1})
    assert login_capacity._active_worker_leases(tmp_path) == 1


def test_active_login_blocks_same_profile_even_with_capacity_two(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOGIN_MAX_SESSIONS', 2)
    write_json_file(tmp_path / 'users/alice/zhihuishu_login_session.json', {'status': 'ready'})
    with pytest.raises(login_capacity.LoginCapacityError):
        with login_capacity.account_profile_lock(tmp_path, 'alice', for_worker=True):
            pytest.fail('profile held by login container')
    with login_capacity.account_profile_lock(tmp_path, 'bobby', for_worker=True):
        pass


def test_missing_course_structure_is_failure_even_if_dom_fallback_is_empty(monkeypatch):
    class Page:
        url = zhihuishu_browser.ASSIGNMENTS_URL
        def goto(self, *args, **kwargs):
            pass
        def evaluate(self, *args, **kwargs):
            return []
    monkeypatch.setattr(zhihuishu_browser.time, 'sleep', lambda _: None)
    monkeypatch.setattr(zhihuishu_browser, '_wait_for_spa', lambda _: None)
    monkeypatch.setattr(zhihuishu_browser, '_collect_smart_course_links', lambda _: [])
    result = zhihuishu_browser._fetch_assignments_page(Page(), 'alice')
    assert result.ok is False and result.items == []


def test_worker_parent_does_not_write_back_to_reregistered_account(isolated_data):
    auth.register('alice', 'password1')
    zhihuishu_store.save_status('alice', {'session': 'active'})
    def replace_account(username, dry_run=False):
        assert auth.delete_account(username, 'password1', auth.DELETE_CONFIRMATION)[0]
        assert auth.register(username, 'password2')[0]
        zhihuishu_store.save_status(username, {'session': 'active', 'last_error': 'new identity'})
        return False
    zhihuishu_worker._run_all_users_round({}, runner=replace_account)
    status = zhihuishu_store.load_status('alice')
    assert status['last_error'] == 'new identity'
    assert not status.get('failure_count') and not status.get('next_attempt_at')


def test_worker_child_receives_immutable_identity(isolated_data, monkeypatch):
    auth.register('alice', 'password1')
    zhihuishu_store.save_status('alice', {'session': 'active'})
    commands = []
    class Process:
        def __init__(self, command, **kwargs):
            commands.append(command)
        def wait(self, timeout):
            return 0
    monkeypatch.setattr(zhihuishu_worker.subprocess, 'Popen', Process)
    assert zhihuishu_worker._run_user_subprocess('alice')
    command = commands[0]
    assert command[command.index('--account-id') + 1] == auth.session_identity('alice')[0]
    assert '--connection-revision' in command
    assert zhihuishu_worker.main(['--child-cycle', '--once', '--username', 'alice',
                                  '--account-id', 'old-account', '--connection-revision', '0']) == 1


@pytest.mark.parametrize('module, filename', [
    (zhihuishu_login_sessions, 'zhihuishu_login_session.json'),
    (tongji_login_sessions, 'tongji_login_session.json'),
])
def test_stale_session_cleanup_preserves_new_window(isolated_data, monkeypatch, module, filename):
    path = isolated_data / 'users/alice' / filename
    old = {'username': 'alice', 'token': 'old-token', 'container_name': 'old-container'}
    new = {'username': 'alice', 'token': 'new-token', 'container_name': 'new-container'}
    write_json_file(path, new)
    monkeypatch.setattr(module, '_stop_container', lambda _: pytest.fail('new window stopped'))
    assert not module._remove_session_file(path, old)
    assert read_json_file(path, None) == new
