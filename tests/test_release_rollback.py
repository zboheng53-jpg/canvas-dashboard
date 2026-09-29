"""Exercise the installer's real activation/verification block without a server."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("failure", ["activate", "local-health", "https", "service", "none"])
def test_every_activation_verification_failure_restores_previous_release(tmp_path, failure):
    bash = Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else shutil.which("bash")
    if not bash or not Path(bash).exists():
        pytest.skip("Bash is required to exercise production shell control flow")
    source = (Path(__file__).parents[1] / "deploy" / "install-release.sh").read_text(encoding="utf-8")
    block = source[source.index("rollback_on_failure() {"):source.index("if ! prune_old_releases;")]
    script = tmp_path / "exercise.sh"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
release=new
previous=old
root=${2:?temporary deployment root required}
prior_previous=older
failure=$1
activate_release() {
    echo "activated:$1"
    if [ "$1" = new ] && [ "$failure" = activate ]; then return 1; fi
}
sudo() { return 0; }
sleep() { return 0; }
seq() { for ((number=$1; number<=$2; number++)); do echo "$number"; done; }
curl() {
    case "$*" in
        *https:*) [ "$failure" != https ] ;;
        *) [ "$failure" != local-health ] ;;
    esac
}
systemctl() {
    if [ "$failure" = service ] && [[ "$*" == *canvas-dashboard-backup.timer* ]]; then
        return 1
    fi
    return 0
}
""" + block,
        encoding="utf-8",
    )
    marker = tmp_path / ".previous-release"
    marker.write_text("old\n", encoding="utf-8")
    result = subprocess.run([str(bash), script.as_posix(), failure, tmp_path.as_posix()], capture_output=True, text=True, timeout=15)
    assert "activated:new" in result.stdout
    if failure == "none":
        assert result.returncode == 0, result.stderr
        assert "activated:old" not in result.stdout
        assert marker.read_text(encoding="utf-8").strip() == "old"
    else:
        assert result.returncode != 0
        assert "activated:old" in result.stdout, result.stderr
        assert marker.read_text(encoding="utf-8").strip() == "older"
