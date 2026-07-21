from pathlib import Path


def test_local_preview_script_has_safe_local_defaults():
    script = Path(__file__).parents[1] / "scripts" / "local-preview.ps1"
    text = script.read_text(encoding="utf-8")

    assert '[int]$Port = 5000' in text
    assert 'http://127.0.0.1:$Port' in text
    assert 'Invoke-WebRequest' in text
    assert '[switch]$NoBrowser' in text
    assert 'cmd.exe' in text
    assert 'CANVAS_DASHBOARD_PORT' in text


def test_local_preview_batch_launcher_bypasses_only_its_own_execution_policy():
    launcher = Path(__file__).parents[1] / "local-preview.bat"
    text = launcher.read_text(encoding="utf-8")

    assert "-ExecutionPolicy Bypass" in text
    assert "local-preview.ps1" in text
