from pathlib import Path
import subprocess
import shutil

import pytest


def test_local_powershell_scripts_pin_venv_and_utf8():
    repo_root = Path(__file__).parents[1]
    dev_script = repo_root / "scripts" / "dev.ps1"
    test_script = repo_root / "scripts" / "test.ps1"

    for script in (dev_script, test_script):
        text = script.read_text(encoding="utf-8")
        assert ".venv" in text
        assert "PYTHONUTF8" in text
        assert "OutputEncoding" in text

    assert "-m pytest" in test_script.read_text(encoding="utf-8")
    assert "app.py" in dev_script.read_text(encoding="utf-8")


def test_default_test_run_only_collects_the_repository_test_suite():
    repo_root = Path(__file__).parents[1]
    test_script = (repo_root / "scripts" / "test.ps1").read_text(encoding="utf-8")

    assert '$PytestArgs = @("tests", "-q")' in test_script


def test_test_script_uses_a_unique_system_temp_directory():
    repo_root = Path(__file__).parents[1]
    test_script = (repo_root / "scripts" / "test.ps1").read_text(encoding="utf-8")

    assert "[System.IO.Path]::GetTempPath()" in test_script
    assert '"canvas-dashboard-pytest-" + [Guid]::NewGuid().ToString("N")' in test_script
    assert "$env:TEMP = $TestTempRoot" in test_script
    assert "$env:TMP = $TestTempRoot" in test_script
    assert "Remove-Item -LiteralPath $TestTempRoot -Recurse -Force" in test_script


def test_deploy_script_runs_repository_regression_gate_and_compile_check():
    repo_root = Path(__file__).parents[1]
    deploy_script = repo_root / ".agents" / "skills" / "deploy-canvas-dashboard" / "scripts" / "deploy.ps1"
    text = deploy_script.read_text(encoding="utf-8")

    assert ".\\scripts\\test.ps1" in text
    assert 'git ls-files -- "*.py"' in text
    assert "-m py_compile" in text
    assert "-m compileall" not in text
    assert "unittest discover" not in text
    assert "StrictHostKeyChecking=no" not in text
    assert "StrictHostKeyChecking=yes" in text
    assert "UserKnownHostsFile=" in text
    assert "install-release.sh" in text
    assert "--resolve canvas-dashboard.xyz:443:127.0.0.1" in text


def test_repository_pins_the_production_ed25519_host_key():
    repo_root = Path(__file__).parents[1]
    known_hosts = (repo_root / "deploy" / "known_hosts").read_text(encoding="utf-8")

    assert known_hosts.startswith("124.222.188.101 ssh-ed25519 ")
    assert "*" not in known_hosts


def test_apple_calendar_mobile_test_script_has_a_non_network_dry_run():
    repo_root = Path(__file__).parents[1]
    script = repo_root / "scripts" / "apple-calendar-mobile-test.ps1"

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-DryRun"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Dry run passed" in result.stdout


def test_apple_calendar_mobile_test_script_uses_an_isolated_port():
    repo_root = Path(__file__).parents[1]
    text = (repo_root / "scripts" / "apple-calendar-mobile-test.ps1").read_text(encoding="utf-8")

    assert "[System.Net.Sockets.TcpListener]" in text
    assert "port=5051" not in text


@pytest.mark.parametrize("has_evidence,force,require_evidence,expected_tests,ok", [
    (True, False, False, 0, True), (False, False, False, 1, True),
    (True, True, False, 1, True), (False, False, True, 0, False),
])
def test_deploy_reuses_evidence_or_runs_once(tmp_path, has_evidence, force, require_evidence, expected_tests, ok):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows deploy runner")
    root = Path(__file__).parents[1]
    source = (root / ".agents/skills/deploy-canvas-dashboard/scripts/deploy.ps1").read_text(encoding="utf-8")
    block = source[source.index("$HasEvidence ="):source.index("$PythonFiles =")]
    block = block.replace(r".\.venv\Scripts\python.exe", "Invoke-PythonMock").replace("powershell.exe", "Invoke-TestMock")
    script = tmp_path / "evidence.ps1"
    boolean = lambda value: "$true" if value else "$false"
    script.write_text(f"""$ErrorActionPreference = 'Stop'
$ReleaseCommit = 'abc'
$ForceLocalRegression = {boolean(force)}
$SkipLocalRegression = {boolean(require_evidence)}
$script:EvidenceAvailable = {boolean(has_evidence)}
function Invoke-PythonMock {{
    if ($script:EvidenceAvailable) {{ $global:LASTEXITCODE = 0; Write-Output 'abc' }}
    else {{ $global:LASTEXITCODE = 1 }}
}}
function Invoke-TestMock {{
    Write-Output 'TEST_EXECUTED'
    $script:EvidenceAvailable = $true
    $global:LASTEXITCODE = 0
}}
{block}
""", encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=15)
    assert (result.returncode == 0) == ok, result.stdout + result.stderr
    assert result.stdout.count("TEST_EXECUTED") == expected_tests


def test_deploy_does_not_retry_uncertain_activation(tmp_path):
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows deploy runner")
    root = Path(__file__).parents[1]
    source = (root / ".agents/skills/deploy-canvas-dashboard/scripts/deploy.ps1").read_text(encoding="utf-8")
    assert 'Invoke-DeploySsh -Command $RemoteCommand -Attempts 1' in source
    assert 'retire-unused-apps.sh' not in source
    block = source[source.index("function Invoke-DeploySsh"):source.index("function Send-DeployArchive")]
    script = tmp_path / "retry.ps1"
    script.write_text("""$ErrorActionPreference = 'Stop'
function ssh { Write-Output 'SSH_EXECUTED'; $global:LASTEXITCODE = 255 }
function Start-Sleep { }
""" + block + "\nInvoke-DeploySsh -Command 'mock' -Description 'activation' -Attempts 1\n", encoding="utf-8")
    result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert result.stdout.count("SSH_EXECUTED") == 1
