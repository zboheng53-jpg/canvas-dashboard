"""Exercise workflow safeguards without contacting production or real user data."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from scripts.check_release import check_release, git
from scripts import check_release as release_checks
from scripts import recommend_tests

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
    assert count == {"empty": 0, "normal": 6, "dense": 36}[scenario]


def test_deploy_pins_checked_commit_before_packaging():
    source = (ROOT / ".agents/skills/deploy-canvas-dashboard/scripts/deploy.ps1").read_text(encoding="utf-8-sig")
    assert source.index("scripts\\check_release.py") < source.index("-File .\\scripts\\test.ps1")
    assert source.index("--expected $ReleaseCommit") < source.index("git archive")
    assert "--output=$TarFile $ReleaseCommit" in source


def test_changed_selection_includes_deletions_and_committed_branch_changes(release_repo):
    assert recommend_tests.diff_worktree(release_repo) == []
    (release_repo / "app.txt").unlink()
    assert recommend_tests.diff_worktree(release_repo) == ["app.txt"]
    catalog = recommend_tests.build_catalog(ROOT)
    assert recommend_tests.classify("app.txt", catalog, release_repo).tests == ("tests",)
    git(release_repo, "add", "-u")
    git(release_repo, "commit", "-m", "delete")
    assert recommend_tests.diff_staged(release_repo) == []
    assert recommend_tests.diff_against_parent(release_repo) == ["app.txt"]
    result = subprocess.run([sys.executable, str(ROOT / "scripts/recommend_tests.py"),
                             "--repo", str(release_repo), "--base", "origin/main", "--pytest-args"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "tests"


def test_changed_selection_git_errors_do_not_look_like_no_changes(tmp_path):
    with pytest.raises(recommend_tests.SelectionError):
        recommend_tests.diff_worktree(tmp_path)


def test_module_iteration_does_not_pull_in_unrelated_browser_tests():
    catalog = recommend_tests.build_catalog(ROOT)
    selection = recommend_tests.classify("haoke_client.py", catalog, ROOT)
    assert selection.tests == ("tests/test_haoke_client.py", "tests/test_haoke_api.py")
    assert recommend_tests.classify("storage.py", catalog, ROOT).suite == "acceptance"


def _record_evidence(repo, name, **overrides):
    folder = repo / "test-results" / name
    folder.mkdir(parents=True)
    manifest = dict(schema_version=2, full_suite=True, commit="abc", end_commit="abc",
                    dirty=False, end_dirty=False, environment="env", suite="all",
                    exit_code=0, collection_only=False,
                    started_at=f"2026-09-30T{name[9:11]}:{name[11:13]}:{name[13:15]}+00:00")
    manifest.update(overrides)
    (folder / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "results.xml").write_text(
        '<testsuite tests="1" failures="0" errors="0"><testcase name="passed"/></testsuite>', encoding="utf-8")
    (folder / "pytest.log").write_text("", encoding="utf-8")
    return folder


@pytest.fixture
def evidence_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(release_checks, "check_release", lambda *_: "abc")
    monkeypatch.setattr(release_checks, "environment_fingerprint", lambda: "env")
    return tmp_path


@pytest.mark.parametrize("overrides", [
    {"full_suite": False}, {"schema_version": 1}, {"end_commit": "other"},
    {"end_dirty": True}, {"dirty": True}, {"environment": "changed"},
    {"exit_code": None}, {"exit_code": 1}, {"collection_only": True}, {"suite": "ui"},
])
def test_release_evidence_rejects_incomplete_partial_or_stale_runs(evidence_repo, overrides):
    _record_evidence(evidence_repo, "20260930-100000-11111111", **overrides)
    with pytest.raises(RuntimeError, match="No recorded full-suite"):
        release_checks.check_test_evidence(evidence_repo)


def test_release_evidence_never_falls_back_after_newer_failure_or_interruption(evidence_repo):
    _record_evidence(evidence_repo, "20260930-100000-11111111")
    assert release_checks.check_test_evidence(evidence_repo) == "abc"
    # A successful targeted run is feedback, not replacement full-suite evidence.
    _record_evidence(evidence_repo, "20260930-110000-22222222", full_suite=False)
    assert release_checks.check_test_evidence(evidence_repo) == "abc"
    _record_evidence(evidence_repo, "20260930-120000-33333333", exit_code=None)
    with pytest.raises(RuntimeError, match="exit_code"):
        release_checks.check_test_evidence(evidence_repo)


def test_evidence_orders_concurrent_runs_by_start_and_rejects_corrupt_newer_run(evidence_repo):
    _record_evidence(evidence_repo, "20260930-100000-ffffffff", started_at="2026-09-30T10:00:00.1+00:00")
    later = _record_evidence(evidence_repo, "20260930-100000-00000000", exit_code=1,
                             started_at="2026-09-30T10:00:00.2+00:00")
    with pytest.raises(RuntimeError, match="exit_code"):
        release_checks.check_test_evidence(evidence_repo)
    (later / "run.json").write_text("{interrupted", encoding="utf-8")
    os.utime(later / "run.json", (2000000000, 2000000000))
    with pytest.raises(RuntimeError, match="Unreadable newer evidence"):
        release_checks.check_test_evidence(evidence_repo)


@pytest.mark.parametrize("xml", [
    '<testsuite tests="1" failures="1" errors="0"><testcase name="bad"><failure/></testcase></testsuite>',
    '<testsuite tests="2" failures="0" errors="0"><testcase name="missing"/></testsuite>',
    '<testsuite tests="1" failures="0" errors="0"><testcase name="skipped"><skipped/></testcase></testsuite>',
])
def test_release_evidence_requires_actual_junit_success(evidence_repo, xml):
    folder = _record_evidence(evidence_repo, "20260930-100000-11111111")
    (folder / "results.xml").write_text(xml, encoding="utf-8")
    with pytest.raises(RuntimeError, match="results.xml"):
        release_checks.check_test_evidence(evidence_repo)


def test_real_runner_distinguishes_full_partial_and_source_changed(release_repo):
    """Use the actual PowerShell entry point and pytest, in a disposable tiny repo."""
    import shutil
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows runner contract")
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", "--without-pip",
                    str(release_repo / ".venv")], check=True, capture_output=True)
    import site
    # A venv created from another venv inherits the base interpreter's site-packages,
    # not the parent venv's dependencies. Reuse our installed test packages offline.
    (release_repo / ".venv/Lib/site-packages/parent-tests.pth").write_text(
        "\n".join(site.getsitepackages()), encoding="utf-8")
    (release_repo / "scripts").mkdir()
    for name in ("test.ps1", "resolve-python.ps1", "check_release.py", "clean_test_artifacts.py", "recommend_tests.py"):
        shutil.copy2(ROOT / "scripts" / name, release_repo / "scripts" / name)
    (release_repo / "tests").mkdir()
    (release_repo / "tests/conftest.py").write_text(
        'def pytest_addoption(parser):\n    parser.addoption("--suite", default="all")\n', encoding="utf-8")
    (release_repo / "tests/test_sample.py").write_text(
        'import os\nfrom pathlib import Path\ndef test_sample():\n'
        '    if os.environ.get("CDB_TEST_MUTATE"):\n'
        '        Path("app.txt").write_text("changed during pytest")\n'
        '    assert True\n', encoding="utf-8")
    (release_repo / ".gitignore").write_text(".venv/\ntest-results/\n__pycache__/\n", encoding="utf-8")
    git(release_repo, "add", ".")
    git(release_repo, "commit", "-m", "runner fixture")

    def run(*args, mutate=False, checkout=release_repo):
        env = dict(os.environ, PYTHONUTF8="1")
        env.pop("PYTEST_ADDOPTS", None)
        env.pop("PYTEST_PLUGINS", None)
        if mutate:
            env["CDB_TEST_MUTATE"] = "1"
        result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                 str(checkout / "scripts/test.ps1"), "-Workers", "1", *args],
                                cwd=checkout, env=env, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stdout + result.stderr
        paths = list((checkout / "test-results").glob("*/run.json"))
        return json.loads(max(paths, key=lambda path: path.stat().st_mtime_ns).read_text(encoding="utf-8-sig"))

    full = run()
    assert full["full_suite"] is True and full["end_dirty"] is False
    assert full["environment"] and full["end_commit"] == full["commit"]
    verification = subprocess.run([
        str(release_repo / ".venv/Scripts/python.exe"), "scripts/check_release.py",
        "--test-evidence", "--local-only"], cwd=release_repo, capture_output=True, text=True)
    assert verification.returncode == 0, verification.stdout + verification.stderr
    run("-ChangedOnly")
    assert len(list((release_repo / "test-results").glob("*/run.json"))) == 1
    partial = run("-PytestArgs", "tests/test_sample.py")
    assert partial["full_suite"] is False
    linked = release_repo.parent / "parallel task"
    git(release_repo, "worktree", "add", "-b", "codex/parallel", str(linked))
    linked_run = run("-PytestArgs", "tests/test_sample.py", mutate=True, checkout=linked)
    assert linked_run["end_dirty"] is True
    assert (release_repo / "app.txt").read_text() == "first"
    assert (linked / "app.txt").read_text() == "changed during pytest"
    assert not (linked / ".venv").exists()

    def resolve():
        return subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               str(linked / "scripts/resolve-python.ps1")],
                              cwd=linked, capture_output=True, text=True, timeout=15)

    (linked / "requirements.txt").write_text("dependency-change", encoding="utf-8")
    incompatible = resolve()
    assert incompatible.returncode != 0
    assert "Dependency files differ" in incompatible.stderr
    # A local environment is always preferred, including dependency experiments.
    local_python = linked / ".venv/Scripts/python.exe"
    local_python.parent.mkdir(parents=True)
    local_python.write_text("path-resolution fixture only", encoding="utf-8")
    preferred = resolve()
    assert preferred.returncode == 0, preferred.stderr
    assert str(local_python) in preferred.stdout
    changed = run(mutate=True)
    assert changed["dirty"] is False and changed["end_dirty"] is True


def test_automatic_retention_preserves_current_failed_unknown_and_foreign_dirs(tmp_path, monkeypatch):
    from scripts import clean_test_artifacts as cleanup
    current = _record_evidence(tmp_path, "20260930-080000-11111111")
    old = _record_evidence(tmp_path, "20260930-090000-22222222")
    failed = _record_evidence(tmp_path, "20260930-100000-33333333", exit_code=1)
    unknown = _record_evidence(tmp_path, "20260930-110000-44444444", exit_code=None)
    newest = _record_evidence(tmp_path, "20260930-120000-55555555")
    foreign = _record_evidence(tmp_path, "manual-evidence")
    monkeypatch.setattr(cleanup, "directory_size", lambda *_: pytest.fail("automatic retention must not scan all artifacts"))
    assert cleanup.rotate_runs(tmp_path, current.name, 0, 30) == 0
    assert not old.exists()
    assert all(path.exists() for path in (current, failed, unknown, newest, foreign))
