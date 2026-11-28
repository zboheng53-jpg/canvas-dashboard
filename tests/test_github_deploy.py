from pathlib import Path


def _read(repo_root: Path, *parts: str) -> str:
    return repo_root.joinpath(*parts).read_text(encoding="utf-8")


def test_deploy_workflow_requires_tests_and_production_environment():
    repo_root = Path(__file__).parents[1]
    workflow = _read(repo_root, ".github", "workflows", "deploy.yml")

    assert "branches: [main]" in workflow
    assert "needs: tests" in workflow
    assert "name: production" in workflow
    assert "contents: read" in workflow
    assert "deploy/known_hosts" in workflow
    runs = [
        line
        for line in workflow.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any("git pull" in line for line in runs)
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in workflow
    assert '"$main_sha" != "$GITHUB_SHA"' in workflow
    assert "sudo -n /usr/local/sbin/canvas-deploy release" in workflow
    assert "sha256sum" in workflow


def test_rollback_workflow_switches_releases_instead_of_reverting_commits():
    repo_root = Path(__file__).parents[1]
    workflow = _read(repo_root, ".github", "workflows", "rollback.yml")

    assert "workflow_dispatch:" in workflow
    assert "name: production" in workflow
    assert "canvas-deploy rollback" in workflow
    assert 'target=${TARGET#/home/ubuntu/canvas-dashboard/releases/}' in workflow
    assert "'$target'" in workflow
    assert "git revert" not in workflow


def test_deploy_wrapper_validates_input_and_runs_the_ubuntu_installer():
    repo_root = Path(__file__).parents[1]
    wrapper = _read(repo_root, "deploy", "github-deploy", "canvas-deploy")

    assert "release_pattern='^release-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$'" in wrapper
    assert 'runuser -u deploy -- cat -- "$upload" | as_ubuntu tee "$archive"' in wrapper
    assert 'actual=$(as_ubuntu sha256sum "$archive"' in wrapper
    assert 'as_ubuntu tar -xzf "$archive"' in wrapper
    assert "runuser -u ubuntu -- env HOME=/home/ubuntu" in wrapper
    assert "run-backup.sh" in wrapper
    assert "install-release.sh" in wrapper
    assert "rollback-release.sh" in wrapper
    assert 'name=${target#"$root/releases/"}' in wrapper
    assert 'target="$root/releases/$name"' in wrapper


def test_deploy_user_setup_grants_only_the_wrapper():
    repo_root = Path(__file__).parents[1]
    setup = _read(repo_root, "deploy", "github-deploy", "setup-deploy-user.sh")

    assert "deploy ALL=(root) NOPASSWD: /usr/local/sbin/canvas-deploy" in setup
    assert setup.index('visudo -cf "$sudoers_file"') < setup.index(
        'install -o root -g root -m 0440 "$sudoers_file" /etc/sudoers.d/canvas-deploy'
    )
    assert "passwd -l deploy" in setup
    assert "install -o root -g root -m 0755" in setup


def test_codeowners_and_export_rules_protect_deploy_configuration():
    repo_root = Path(__file__).parents[1]
    codeowners = _read(repo_root, ".github", "CODEOWNERS")
    attributes = _read(repo_root, ".gitattributes")

    assert "/deploy/ @zboheng53-jpg" in codeowners
    assert "/.github/ @zboheng53-jpg" in codeowners
    assert "deploy/github-deploy export-ignore" in attributes
