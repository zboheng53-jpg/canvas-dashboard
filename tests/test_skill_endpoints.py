import subprocess
import sys
from pathlib import Path
import pytest
import app as dashboard_app


@pytest.fixture
def client():
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def test_skill_public_endpoints(client):
    # Public endpoints should NOT require session login
    resp = client.get("/skill/README.md")
    assert resp.status_code == 200
    assert resp.mimetype.startswith("text/markdown")
    text = resp.data.decode("utf-8")
    assert "Canvas Dashboard Agent Skill" in text
    assert "请安装 Canvas Dashboard Skill" in text
    # Checks dynamic interpolation of host url
    assert "http://localhost/skill/README.md" in text

    # Alias /skill and /skill/
    resp_alias = client.get("/skill")
    assert resp_alias.status_code == 200
    assert b"Canvas Dashboard Agent Skill" in resp_alias.data

    # SKILL.md
    resp = client.get("/skill/SKILL.md")
    assert resp.status_code == 200
    skill_text = resp.data.decode("utf-8")
    assert "name: canvas-dashboard" in skill_text
    assert "canvas_api.py" in skill_text

    # canvas_api.py
    resp = client.get("/skill/canvas_api.py")
    assert resp.status_code == 200
    compile(resp.data, "canvas_api.py", "exec")

    # install.sh
    resp = client.get("/skill/install.sh")
    assert resp.status_code == 200
    assert b"install.sh --server" in resp.data

    # install.ps1
    resp = client.get("/skill/install.ps1")
    assert resp.status_code == 200
    assert b"CmdletBinding" in resp.data


def test_skill_path_traversal_forbidden(client):
    resp = client.get("/skill/../app.py")
    assert resp.status_code == 404

    resp = client.get("/skill/nonexistent_file.xyz")
    assert resp.status_code == 404


def test_canvas_api_cli_help():
    script_path = Path(__file__).parent.parent / "skill" / "canvas_api.py"
    res = subprocess.run([sys.executable, str(script_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Canvas Dashboard Skill API Client" in res.stdout
    assert "today" in res.stdout
    assert "todos" in res.stdout
    assert "add-todo" in res.stdout
