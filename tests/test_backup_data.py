import json
import subprocess
from pathlib import Path

import pytest


def _run_backup_cli(repo_root: Path, *args: str):
    return subprocess.run(
        [str(repo_root / ".venv" / "Scripts" / "python.exe"), str(repo_root / "scripts" / "backup_data.py"), *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_encrypted_backup_round_trip_and_manifest(tmp_path):
    repo_root = Path(__file__).parents[1]
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    source = tmp_path / "data"
    source.mkdir()
    (source / "users.json").write_text('{"alice": {"password_hash": "secret"}}', encoding="utf-8")
    user_dir = source / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "custom_todos.json").write_text('[{"id": 1, "text": "keep me"}]', encoding="utf-8")
    (user_dir / "canvas_cache.json").write_text('[{"id": 99}]', encoding="utf-8")
    (user_dir / "zhihuishu_chromium_profile").mkdir()
    (user_dir / "zhihuishu_chromium_profile" / "Cookies").write_bytes(b"large disposable profile")
    (user_dir / "tongji_login_profile").mkdir()
    (user_dir / "tongji_login_profile" / "Cookies").write_bytes(b"temporary authentication cookies")
    (user_dir / "tongji_login_profile" / "SingletonLock").write_text("active-browser-lock", encoding="utf-8")
    # Runtime state can be incomplete while a login window is being written.
    (user_dir / "tongji_login_session.json").write_text('{"token": ', encoding="utf-8")

    generated = _run_backup_cli(
        repo_root,
        "keygen",
        "--private-key",
        str(private_key),
        "--public-key",
        str(public_key),
    )
    assert generated.returncode == 0, generated.stderr

    backup_dir = tmp_path / "backups"
    created = _run_backup_cli(
        repo_root,
        "create",
        "--data-dir",
        str(source),
        "--output-dir",
        str(backup_dir),
        "--public-key",
        str(public_key),
        "--retention",
        "2",
    )
    assert created.returncode == 0, created.stderr
    backups = list(backup_dir.glob("*.cdbak"))
    assert len(backups) == 1
    assert b"keep me" not in backups[0].read_bytes()

    verified = _run_backup_cli(
        repo_root,
        "verify",
        "--input",
        str(backups[0]),
        "--private-key",
        str(private_key),
    )
    assert verified.returncode == 0, verified.stderr
    summary = json.loads(verified.stdout)
    assert summary["file_count"] == 2

    restored_dir = tmp_path / "restored"
    restored = _run_backup_cli(
        repo_root,
        "restore",
        "--input",
        str(backups[0]),
        "--private-key",
        str(private_key),
        "--output-dir",
        str(restored_dir),
    )
    assert restored.returncode == 0, restored.stderr
    assert json.loads((restored_dir / "data" / "users.json").read_text(encoding="utf-8"))["alice"]
    assert json.loads(
        (restored_dir / "data" / "users" / "alice" / "custom_todos.json").read_text(encoding="utf-8")
    )[0]["text"] == "keep me"
    assert not (restored_dir / "data" / "users" / "alice" / "canvas_cache.json").exists()
    assert not (restored_dir / "data" / "users" / "alice" / "zhihuishu_chromium_profile").exists()
    assert not (restored_dir / "data" / "users" / "alice" / "tongji_login_profile").exists()
    assert not (restored_dir / "data" / "users" / "alice" / "tongji_login_session.json").exists()


def test_restore_reapplies_deletion_ledger_without_removing_recreated_account(tmp_path):
    from scripts.backup_data import apply_deletion_ledger

    source = tmp_path / "restored-data"
    source.mkdir()
    users = {
        "alice": {"account_id": "deleted-id"},
        "bob": {"account_id": "new-id"},
    }
    (source / "users.json").write_text(json.dumps(users), encoding="utf-8")
    for username in users:
        directory = source / "users" / username
        directory.mkdir(parents=True)
        (directory / "custom_todos.json").write_text("[]", encoding="utf-8")
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"deleted_accounts": {"deleted-id": {}, "old-bob-id": {}}}), encoding="utf-8")

    assert apply_deletion_ledger(source, ledger) == ["alice"]
    assert not (source / "users" / "alice").exists()
    assert (source / "users" / "bob" / "custom_todos.json").exists()
    assert json.loads((source / "users.json").read_text(encoding="utf-8")) == {"bob": users["bob"]}


def test_restore_refuses_missing_or_invalid_explicit_deletion_ledger(tmp_path):
    from scripts.backup_data import apply_deletion_ledger

    ledger = tmp_path / "ledger.json"
    with pytest.raises(FileNotFoundError):
        apply_deletion_ledger(tmp_path / "data", ledger)
    ledger.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="deleted_accounts"):
        apply_deletion_ledger(tmp_path / "data", ledger)


def test_restore_keeps_newer_local_deletions_when_an_older_guard_is_supplied(tmp_path):
    from scripts.backup_data import apply_deletion_ledger

    restored = tmp_path / "data"
    restored.mkdir()
    users = {"alice": {"account_id": "older-deletion"}, "bob": {"account_id": "newer-deletion"}, "carol": {"account_id": "live"}}
    (restored / "users.json").write_text(json.dumps(users), encoding="utf-8")
    (restored / ".account_deletion_ledger.json").write_text(json.dumps({"deleted_accounts": {"newer-deletion": {}}}), encoding="utf-8")
    older_guard = tmp_path / "older-ledger.json"
    older_guard.write_text(json.dumps({"deleted_accounts": {"older-deletion": {}}}), encoding="utf-8")

    assert set(apply_deletion_ledger(restored, older_guard)) == {"alice", "bob"}
    assert set(json.loads((restored / "users.json").read_text(encoding="utf-8"))) == {"carol"}
    saved = json.loads((restored / ".account_deletion_ledger.json").read_text(encoding="utf-8"))
    assert set(saved["deleted_accounts"]) == {"older-deletion", "newer-deletion"}


def test_restore_reports_account_data_cleanup_failure(tmp_path, monkeypatch):
    from scripts import backup_data

    source = tmp_path / "data"
    directory = source / "users" / "alice"
    directory.mkdir(parents=True)
    users = {"alice": {"account_id": "deleted-id"}}
    (source / "users.json").write_text(json.dumps(users), encoding="utf-8")
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"deleted_accounts": {"deleted-id": {}}}), encoding="utf-8")

    def fail_cleanup(path):
        raise PermissionError("account directory is occupied")

    monkeypatch.setattr(backup_data.shutil, "rmtree", fail_cleanup)
    with pytest.raises(PermissionError, match="occupied"):
        backup_data.apply_deletion_ledger(source, ledger)
    assert json.loads((source / "users.json").read_text(encoding="utf-8")) == users


def test_offsite_guard_prevents_old_snapshot_account_and_credential_revival(tmp_path):
    from scripts import backup_data

    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    backup_data.keygen(private_key, public_key)
    source = tmp_path / "server-data"
    source.mkdir()
    users = {
        "alice": {"account_id": "deleted-id", "session_version": 2, "password_hash": "old-password"},
        "bob": {"account_id": "kept-id", "session_version": 4, "password_hash": "kept-password", "reset_token_hash": "revoked-reset", "reset_expires_at": "2099-01-01T00:00:00+08:00"},
    }
    (source / "users.json").write_text(json.dumps(users), encoding="utf-8")
    (source / ".flask_secret_key").write_text("old-session-key", encoding="utf-8")
    (source / ".encryption_key").write_bytes(b"preserve-platform-key")
    for username in users:
        directory = source / "users" / username
        directory.mkdir(parents=True)
        for filename in ("agent_token.json", "apple_calendar.json"):
            (directory / filename).write_text('{"token_hash": "revoked-token"}', encoding="utf-8")
    snapshot = backup_data.create_backup(source, tmp_path / "offsite-data", public_key, 2)
    # The deletion happened after the data snapshot. Its separate current guard
    # must be recoverable without consulting anything on the lost server.
    (source / ".account_deletion_ledger.json").write_text(
        json.dumps({"deleted_accounts": {"deleted-id": {"reason": "user request"}}}), encoding="utf-8"
    )
    guard = backup_data.create_recovery_guard(source, tmp_path / "offsite-guards", public_key, 2)
    restored = tmp_path / "restored"
    guard_copy = tmp_path / "guard-copy"
    repo_root = Path(__file__).parents[1]
    guard_result = _run_backup_cli(repo_root, "restore", "--input", str(guard), "--private-key", str(private_key), "--output-dir", str(guard_copy))
    assert guard_result.returncode == 0, guard_result.stderr
    restored_result = _run_backup_cli(repo_root, "restore", "--input", str(snapshot), "--private-key", str(private_key), "--output-dir", str(restored),
                                      "--deletion-ledger", str(guard_copy / "data" / "deletion-ledger.json"))
    assert restored_result.returncode == 0, restored_result.stderr
    assert json.loads(restored_result.stdout)["deleted_accounts_reapplied"] == ["alice"]

    recovered = json.loads((restored / "data" / "users.json").read_text(encoding="utf-8"))
    assert set(recovered) == {"bob"}
    assert recovered["bob"]["session_version"] == 5
    assert recovered["bob"]["password_hash"] == "kept-password"
    assert "reset_token_hash" not in recovered["bob"]
    assert "reset_expires_at" not in recovered["bob"]
    assert "deleted-id" in json.loads((restored / "data" / ".account_deletion_ledger.json").read_text(encoding="utf-8"))["deleted_accounts"]
    assert not (restored / "data" / ".flask_secret_key").exists()
    assert (restored / "data" / ".encryption_key").read_bytes() == b"preserve-platform-key"
    for filename in ("agent_token.json", "apple_calendar.json"):
        assert json.loads((restored / "data" / "users" / "bob" / filename).read_text(encoding="utf-8")) == {}


def test_backup_refuses_corrupt_included_json(tmp_path):
    repo_root = Path(__file__).parents[1]
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    source = tmp_path / "data"
    source.mkdir()
    (source / "users.json").write_text('{"broken": ', encoding="utf-8")
    assert _run_backup_cli(
        repo_root,
        "keygen",
        "--private-key",
        str(private_key),
        "--public-key",
        str(public_key),
    ).returncode == 0

    backup_dir = tmp_path / "backups"
    result = _run_backup_cli(
        repo_root,
        "create",
        "--data-dir",
        str(source),
        "--output-dir",
        str(backup_dir),
        "--public-key",
        str(public_key),
    )

    assert result.returncode != 0
    assert not list(backup_dir.glob("*.cdbak"))


def test_backup_allows_symlinked_data_root_but_refuses_nested_symlink(tmp_path):
    repo_root = Path(__file__).parents[1]
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    real_data = tmp_path / "real-data"
    real_data.mkdir()
    (real_data / "users.json").write_text("{}", encoding="utf-8")
    linked_data = tmp_path / "data"
    try:
        linked_data.symlink_to(real_data, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Creating symlinks requires extra privileges on this Windows host")
        raise

    assert _run_backup_cli(
        repo_root,
        "keygen",
        "--private-key",
        str(private_key),
        "--public-key",
        str(public_key),
    ).returncode == 0
    backup_dir = tmp_path / "backups"
    created = _run_backup_cli(
        repo_root,
        "create",
        "--data-dir",
        str(linked_data),
        "--output-dir",
        str(backup_dir),
        "--public-key",
        str(public_key),
    )
    assert created.returncode == 0, created.stderr

    nested_target = tmp_path / "nested-target.json"
    nested_target.write_text("{}", encoding="utf-8")
    (real_data / "nested-link.json").symlink_to(nested_target)
    refused = _run_backup_cli(
        repo_root,
        "create",
        "--data-dir",
        str(linked_data),
        "--output-dir",
        str(tmp_path / "rejected-backups"),
        "--public-key",
        str(public_key),
    )
    assert refused.returncode != 0
    assert "Symlinks are not allowed" in refused.stderr
