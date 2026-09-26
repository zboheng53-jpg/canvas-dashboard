"""Exercise workflow safeguards without contacting production or real user data."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from scripts.check_release import check_release, git

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def release_repo(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.email", "workflow@example.invalid")
    git(repo, "config", "user.name", "Workflow Test")
    (repo / "app.txt").write_text("first", encoding="utf-8")
    git(repo, "add", "app.txt")
    git(repo, "commit", "-m", "initial")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "origin", "main")
    return repo


def test_release_guard_accepts_only_clean_pushed_main(release_repo):
    commit = check_release(release_repo)
    assert check_release(release_repo, commit) == commit
    (release_repo / "app.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean working tree"):
        check_release(release_repo)
    git(release_repo, "add", "app.txt")
    git(release_repo, "commit", "-m", "next")
    with pytest.raises(RuntimeError, match="differs from origin"):
        check_release(release_repo)
    git(release_repo, "push", "origin", "main")
    with pytest.raises(RuntimeError, match="HEAD changed"):
        check_release(release_repo, commit)
    assert check_release(release_repo) != commit


def test_release_guard_rejects_untracked_source_and_feature_branch(release_repo):
    source = release_repo / "forgotten.py"
    source.write_text("pass", encoding="utf-8")
    with pytest.raises(RuntimeError, match="clean working tree"):
        check_release(release_repo)
    source.unlink()
    git(release_repo, "switch", "-c", "codex/feature")
    with pytest.raises(RuntimeError, match="main branch"):
        check_release(release_repo)


def test_application_import_resolves_every_data_path_inside_override(tmp_path):
    target = tmp_path / "isolated"
    env = dict(os.environ, CANVAS_DASHBOARD_DATA_DIR=str(target))
    code = '''
import json
import app, auth, user_paths, haoke_client, zhixuemeng_client, zhihuishu_store, tongji_oj_client
import zhihuishu_worker, zhihuishu_login_sessions, tongji_login_sessions, serve
paths = [app.DATA_DIR, auth.USERS_FILE, auth.SECRET_KEY_FILE, auth.DELETION_LEDGER_FILE,
         user_paths.DATA_DIR, haoke_client.KEY_FILE, zhixuemeng_client.KEY_FILE,
         tongji_oj_client.KEY_FILE,
         zhihuishu_store.DATA_DIR, zhihuishu_worker.LOCK_FILE,
         zhihuishu_login_sessions.DATA_DIR, tongji_login_sessions.DATA_DIR, serve.LOG_FILE]
print(json.dumps([str(p) for p in paths]))
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert all(Path(p).resolve().is_relative_to(target) for p in json.loads(result.stdout))
    assert (target / ".flask_secret_key").exists()


@pytest.mark.parametrize("scenario", ["normal", "empty", "dense"])
def test_preview_seeds_isolated_scenarios(tmp_path, scenario):
    env = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path), PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "scripts/preview_action_workspace.py", "--scenario", scenario, "--check"],
                            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert "Preview check passed" in result.stdout
    roots = list(tmp_path.glob("canvas-workspace-preview-*"))
    assert len(roots) == 1
    assert json.loads((roots[0] / "preview.json").read_text())["scenario"] == scenario
    todos = roots[0] / "users" / "preview" / "custom_todos.json"
    count = len(json.loads(todos.read_text(encoding="utf-8"))) if todos.exists() else 0
    assert count == {"empty": 0, "normal": 2, "dense": 32}[scenario]


def test_deploy_pins_checked_commit_before_packaging():
    source = (ROOT / ".agents/skills/deploy-canvas-dashboard/scripts/deploy.ps1").read_text(encoding="utf-8-sig")
    assert source.index("scripts\\check_release.py") < source.index("-File .\\scripts\\test.ps1")
    assert source.index("--expected $ReleaseCommit") < source.index("git archive")
    assert "--output=$TarFile $ReleaseCommit" in source
