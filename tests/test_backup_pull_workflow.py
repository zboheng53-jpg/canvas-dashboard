"""Run the real PowerShell backup workflow with all SSH/SCP calls replaced."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import backup_data


@pytest.mark.parametrize("guard_available", [True, False])
def test_backup_pull_requires_and_uses_independent_latest_guard(tmp_path, guard_available):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Operator download workflow requires Windows PowerShell")
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    private = key_dir / "private.pem"
    public = key_dir / "public.pem"
    backup_data.keygen(private, public)
    data = tmp_path / "server-data"
    data.mkdir()
    (data / "users.json").write_text(json.dumps({"alice": {"account_id": "deleted-id"}}), encoding="utf-8")
    snapshot = backup_data.create_backup(data, tmp_path / "server-snapshots", public, 2)
    (data / ".account_deletion_ledger.json").write_text(
        json.dumps({"deleted_accounts": {"deleted-id": {}}}), encoding="utf-8"
    )
    guard = backup_data.create_recovery_guard(data, tmp_path / "server-guards", public, 2)
    runner = tmp_path / "mock-network.ps1"
    runner.write_text("""param([string]$TargetScript)
function ssh {
    $global:LASTEXITCODE = 0
    if ($args[-1] -like '*recovery-guards*') {
        if ($env:CDB_TEST_GUARD_AVAILABLE -eq '1') { Write-Output '/virtual/recovery-guards/guard.cdbak' }
    } else {
        Write-Output '/virtual/snapshot.cdbak'
    }
}
function scp {
    $source = if ($args[-2] -like '*recovery-guards*') { $env:CDB_TEST_GUARD } else { $env:CDB_TEST_SNAPSHOT }
    Copy-Item -LiteralPath $source -Destination $args[-1]
    $global:LASTEXITCODE = 0
}
& $TargetScript -BackupDirectory $env:CDB_TEST_DOWNLOADS -KeyDirectory $env:CDB_TEST_KEYS -RecoveryDrill
""", encoding="utf-8")
    downloads = tmp_path / "downloads"
    env = dict(os.environ, CDB_TEST_GUARD_AVAILABLE="1" if guard_available else "0",
               CDB_TEST_GUARD=str(guard), CDB_TEST_SNAPSHOT=str(snapshot),
               CDB_TEST_DOWNLOADS=str(downloads), CDB_TEST_KEYS=str(key_dir))
    target = Path(__file__).parents[1] / "scripts" / "pull-production-backup.ps1"
    result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner), str(target)],
                            env=env, capture_output=True, text=True, timeout=30)
    if guard_available:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Latest recovery guard verified:" in result.stdout
        assert "Recovery drill passed" in result.stdout
        assert (downloads / "recovery-guards" / "guard.cdbak").exists()
    else:
        assert result.returncode != 0
        assert "No recovery guard is available" in result.stderr
