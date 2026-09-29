from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

import auth
from storage import read_json_file, write_json_file


@pytest.mark.parametrize('first', [True, False])
def test_registration_does_not_publish_identity_when_orphan_isolation_fails(isolated_data, monkeypatch, first):
    if not first:
        assert auth.register('other', 'password1')[0]
    orphan = isolated_data / 'users/alice'
    orphan.mkdir(parents=True)
    (orphan / 'private.json').write_text('{"old": true}', encoding='utf-8')
    monkeypatch.setattr(auth, '_isolate_user_dir', lambda *args, **kwargs: (False, 'locked', None))
    assert auth.register('alice', 'password1') == (False, 'locked')
    assert not auth.user_exists('alice')
    assert (orphan / 'private.json').exists()


def test_failed_ledger_write_retains_data_and_inactive_retry_record(isolated_data, monkeypatch):
    auth.register('alice', 'password1')
    path = isolated_data / 'users/alice/private.json'
    path.write_text('{"private": true}', encoding='utf-8')
    identity = auth.session_identity('alice')
    def fail(*args):
        raise OSError('disk unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(auth, '_record_deletion', fail)
        ok, message = auth.delete_account('alice', 'password1', auth.DELETE_CONFIRMATION)
    assert not ok and '重试' in message
    assert path.exists()
    assert auth.account_metadata('alice')['status'] == 'deleting'
    assert not auth.validate_session_identity('alice', *identity)
    assert auth.retry_pending_deletions() == ['alice']
    assert not path.exists()


def test_slow_resource_cleanup_revokes_identity_without_holding_all_user_registry(isolated_data):
    auth.register('alice', 'password1')
    auth.register('bobby', 'password1')
    before = auth.session_identity('alice')
    started, release = threading.Event(), threading.Event()
    def cleanup():
        started.set()
        assert release.wait(5)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(auth.delete_account, 'alice', 'password1', auth.DELETE_CONFIRMATION, before_delete=cleanup)
        assert started.wait(5)
        try:
            assert auth.account_metadata('alice')['status'] == 'deleting'
            assert not auth.validate_session_identity('alice', *before)
            assert auth.verify_login('bobby', 'password1')
        finally:
            release.set()
        assert future.result() == (True, None)


def test_failed_purge_does_not_reuse_old_data_or_delete_new_account_on_retry(isolated_data, monkeypatch):
    auth.register('alice', 'password1')
    (isolated_data / 'users/alice/private.json').write_text('{"old": true}', encoding='utf-8')
    old_id = auth.account_metadata('alice')['account_id']
    with monkeypatch.context() as patch:
        patch.setattr(auth, '_clean_quarantine_path', lambda _: False)
        ok, message = auth.delete_account('alice', 'password1', auth.DELETE_CONFIRMATION)
    assert ok and '等待' in message
    assert auth.has_pending_quarantine(old_id)
    assert auth.register('alice', 'password2')[0]
    new_id = auth.account_metadata('alice')['account_id']
    assert new_id != old_id
    path = isolated_data / 'users/alice/new.json'
    path.write_text('{"new": true}', encoding='utf-8')
    result = auth.purge_quarantine()
    assert result['purged'] and not result['failed']
    assert path.exists() and auth.account_metadata('alice')['account_id'] == new_id


def test_account_lock_does_not_swallow_or_repeat_body_exceptions(isolated_data):
    calls = []
    with pytest.raises(ValueError, match='original'):
        with auth.account_operation('alice'):
            calls.append(True)
            raise ValueError('original')
    assert calls == [True]
