from pathlib import Path
import subprocess


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


def test_deploy_script_runs_repository_regression_gate_and_compile_check():
    repo_root = Path(__file__).parents[1]
    deploy_script = repo_root / ".agents" / "skills" / "deploy-canvas-dashboard" / "scripts" / "deploy.ps1"
    text = deploy_script.read_text(encoding="utf-8")

    assert ".\\scripts\\test.ps1" in text
    assert "-m compileall" in text
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
