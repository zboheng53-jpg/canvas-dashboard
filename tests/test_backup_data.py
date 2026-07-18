import json
import subprocess
from pathlib import Path


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
