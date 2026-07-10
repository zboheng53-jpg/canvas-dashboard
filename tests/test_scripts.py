from pathlib import Path


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
