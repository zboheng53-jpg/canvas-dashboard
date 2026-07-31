import json
from datetime import datetime, timedelta

import auth
import user_paths


def _configure_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "DELETION_LEDGER_FILE", tmp_path / ".account_deletion_ledger.json")
    monkeypatch.setattr(auth, "ADMIN_AUDIT_FILE", tmp_path / "account_admin_audit.json")
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)


def test_delete_reuse_username_and_restore_ledger_respect_account_id(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    assert auth.register("alice", "password1")[0]
    old_id = auth.account_metadata("alice")["account_id"]
    (tmp_path / "users" / "alice" / "config.json").write_text('{"secret": "encrypted"}', encoding="utf-8")

    assert auth.delete_account("alice", "password1", auth.DELETE_CONFIRMATION) == (True, None)
    assert not auth.user_exists("alice")
    assert not (tmp_path / "users" / "alice").exists()
    assert old_id in json.loads(auth.DELETION_LEDGER_FILE.read_text(encoding="utf-8"))["deleted_accounts"]

    assert auth.register("alice", "password2")[0]
    new_id = auth.account_metadata("alice")["account_id"]
    assert new_id != old_id
    assert auth.apply_deletion_ledger() == []
    assert auth.user_exists("alice")


def test_password_reset_invalidates_site_sessions_without_touching_platform_data(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    assert auth.register("alice", "password1")[0]
    before = auth.session_identity("alice")
    (tmp_path / "users" / "alice" / "config.json").write_text('{"zhixuemeng_token_encrypted": "ciphertext"}', encoding="utf-8")
    token = auth.issue_password_reset("alice", ttl_minutes=30)

    assert auth.reset_password("alice", token, "password2") == (True, None)
    assert not auth.validate_session_identity("alice", *before)
    assert auth.verify_login("alice", "password2")
    assert "ciphertext" in (tmp_path / "users" / "alice" / "config.json").read_text(encoding="utf-8")


def test_purge_requires_old_and_strictly_blank_account(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    assert auth.register("blank", "password1")[0]
    assert auth.register("kept", "password1")[0]
    users = json.loads(auth.USERS_FILE.read_text(encoding="utf-8"))
    old = (datetime.now(auth.CST) - timedelta(days=91)).isoformat()
    users["blank"]["last_login_at"] = old
    users["kept"]["last_login_at"] = old
    auth.USERS_FILE.write_text(json.dumps(users), encoding="utf-8")
    (tmp_path / "users" / "kept").mkdir(parents=True)
    (tmp_path / "users" / "kept" / "custom_todos.json").write_text("[]", encoding="utf-8")

    assert auth.purge_blank_inactive_accounts() == ["blank"]
    assert not auth.user_exists("blank")
    assert auth.user_exists("kept")
