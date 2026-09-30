"""Recommend the smallest test selection that covers the current change.

Changed paths come from git: the last commit by default (``git diff --name-only HEAD~1``), or from
--staged / --files / --files-from-diff (uncommitted work, which is what
``scripts/test.ps1 -ChangedOnly`` uses). Every path maps to a suite plus a one-sentence reason, and
the script prints the exact commands to run. ``--pytest-args`` prints one pytest argument per line
instead, so ``scripts/test.ps1`` can consume the selection directly.

The suite file lists are read from ``tests/conftest.py`` (the ``safety`` and ``ui`` sets) plus the
test modules that request the shared ``browser`` fixture, so this map cannot drift away from the
real suite definitions.

Standard library only:

    python scripts/recommend_tests.py --files storage.py
    python scripts/recommend_tests.py --files frontend/assets/css/design-system.css
    python scripts/recommend_tests.py --files-from-diff --pytest-args
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SUITE_UI = "ui"
SUITE_ACCEPTANCE = "acceptance"
SUITE_ALL = "all"
SUITE_DIRECT = "direct"
SUITE_SCRIPTS = "scripts"
SUITE_ORDER = {SUITE_DIRECT: 0, SUITE_UI: 0, SUITE_SCRIPTS: 1, SUITE_ACCEPTANCE: 2, SUITE_ALL: 3}

# Fallbacks used only when tests/conftest.py cannot be parsed; keep them in sync with the real sets.
FALLBACK_SAFETY = (
    "test_p0_safety.py", "test_security_auth.py", "test_action_workspace.py",
    "test_account_lifecycle.py", "test_project_focus.py", "test_concurrent_writes.py", "test_scripts.py",
    "test_development_workflow.py", "test_deploy_configs.py", "test_login_capacity.py",
    "test_release_onboarding.py", "test_capacity_guard.py", "test_control_components.py",
    "test_design_system_lint.py", "test_css_architecture.py", "test_frontend_text_integrity.py",
    "test_dashboard_localization.py", "test_ui_refactor.py", "test_business_components.py",
    "test_prelaunch_foundations.py", "test_sync_remediation.py", "test_review_remediation_sync_edges.py",
    "test_review_remediation_accounts.py", "test_todo_deadlines.py",
)
FALLBACK_UI = (
    "test_design_system_lint.py", "test_css_architecture.py", "test_frontend_text_integrity.py",
    "test_dashboard_localization.py", "test_control_components.py", "test_component_lab.py",
)

# Extra modules worth running next to the suite selection, mirroring the feature index in
# docs/development.md. Missing files are filtered out, so a rename only costs one note.
MODULE_TESTS: dict[str, tuple[str, ...]] = {
    "storage.py": ("tests/test_concurrent_writes.py", "tests/test_p0_safety.py"),
    "auth.py": ("tests/test_account_lifecycle.py", "tests/test_security_auth.py"),
    "user_paths.py": ("tests/test_account_lifecycle.py", "tests/test_p0_safety.py"),
    "action_contract.py": ("tests/test_action_workspace.py",),
    "workspace_agenda.py": ("tests/test_action_workspace.py", "tests/test_schedule.py"),
    "schedule_store.py": ("tests/test_schedule.py",),
    "project_store.py": ("tests/test_projects.py", "tests/test_project_todos.py", "tests/test_project_focus.py"),
    "recurring_todo_store.py": ("tests/test_recurring_todo_store.py", "tests/test_recurring_todos_api.py"),
    "external_subtasks.py": ("tests/test_external_subtasks.py", "tests/test_custom_todo_subtasks.py"),
    "platform_state.py": ("tests/test_platform_state.py",),
    "platform_sync.py": ("tests/test_session_and_platform_sync.py",),
    "http_sync.py": ("tests/test_session_and_platform_sync.py",),
    "apple_calendar.py": ("tests/test_apple_calendar.py", "tests/test_apple_calendar_api.py"),
    "capacity_guard.py": ("tests/test_capacity_guard.py",),
    "login_capacity.py": ("tests/test_login_capacity.py",),
    "agent_auth.py": ("tests/test_agent_auth.py", "tests/test_agent_api.py"),
    "agent_mcp.py": ("tests/test_agent_mcp.py",),
    "settings.py": ("tests/test_settings.py",),
    "serve.py": ("tests/test_serve.py",),
    "static_assets.py": ("tests/test_static_assets.py",),
    "canvas_auth.py": ("tests/test_canvas_auth.py",),
    "haoke_client.py": ("tests/test_haoke_client.py", "tests/test_haoke_api.py"),
    "zhixuemeng_client.py": ("tests/test_zhixuemeng_client.py",),
    "zhihuishu_store.py": ("tests/test_zhihuishu_store.py", "tests/test_zhihuishu_api.py"),
    "zhihuishu_worker.py": ("tests/test_zhihuishu_worker.py",),
    "zhihuishu_browser.py": ("tests/test_zhihuishu_browser.py",),
    "ketangpai_client.py": ("tests/test_ketangpai.py",),
    "tongji_oj_client.py": ("tests/test_tongji_oj.py",),
    "tongji_login_sessions.py": ("tests/test_tongji_login_sessions.py",),
}

SCRIPT_TESTS: dict[str, tuple[str, ...]] = {
    "scripts/check_release.py": ("tests/test_development_workflow.py", "tests/test_scripts.py"),
    "scripts/test.ps1": ("tests/test_scripts.py", "tests/test_development_workflow.py"),
    "scripts/dev.ps1": ("tests/test_scripts.py",),
    "scripts/check_nginx_boundaries.py": ("tests/test_deploy_configs.py",),
    "scripts/check_test_env.py": ("tests/test_scripts.py", "tests/test_development_workflow.py"),
    "scripts/clean_test_artifacts.py": ("tests/test_scripts.py", "tests/test_development_workflow.py"),
    "scripts/recommend_tests.py": ("tests/test_scripts.py", "tests/test_development_workflow.py"),
    "scripts/backup_data.py": ("tests/test_backup_data.py",),
    "scripts/pull-production-backup.ps1": ("tests/test_backup_pull_workflow.py",),
    "scripts/install-backup-task.ps1": ("tests/test_backup_pull_workflow.py",),
    "scripts/capacity_guard.py": ("tests/test_capacity_guard.py",),
    "scripts/build_assets.py": ("tests/test_static_assets.py",),
    "scripts/preview_action_workspace.py": ("tests/test_development_workflow.py",),
    "scripts/monitor_runtime.py": ("tests/test_scripts.py",),
    "scripts/export_component_lab_preview.py": ("tests/test_component_lab.py",),
    "scripts/export_open_design_preview.py": ("tests/test_open_design_preview.py",),
}
SCRIPT_DEFAULT_TESTS = ("tests/test_scripts.py", "tests/test_development_workflow.py")
PLATFORM_PATTERN = re.compile(
    r"^(?:.*_(?:client|store|worker|browser|sessions|timetable)\.py|platform_[a-z_]+\.py|http_sync\.py)$"
)


class SelectionError(RuntimeError):
    """Raised when git cannot provide the changed paths."""


@dataclass(frozen=True)
class Catalog:
    """Suite membership derived from tests/conftest.py."""

    ui_static: tuple[str, ...]
    safety: tuple[str, ...]
    browser: tuple[str, ...]

    def files(self, suite: str) -> tuple[str, ...]:
        if suite == SUITE_UI:
            return _dedupe(self.ui_static + self.browser)
        if suite == SUITE_ACCEPTANCE:
            return _dedupe(self.safety + self.browser)
        return ("tests",)


@dataclass(frozen=True)
class Recommendation:
    path: str
    suite: str
    reason: str
    tests: tuple[str, ...] = ()
    missing: tuple[str, ...] = field(default=())


def _dedupe(items) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for item in items:
        if item and item not in seen:
            seen[item] = None
    return tuple(seen)


def _literal_file_sets(conftest: Path) -> dict[str, tuple[str, ...]]:
    try:
        tree = ast.parse(conftest.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    found: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {"safety", "ui"}:
            continue
        if not isinstance(node.value, ast.Set):
            continue
        names = tuple(
            element.value for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        )
        if names:
            found[target.id] = names
    return found


def _browser_test_files(tests_dir: Path) -> tuple[str, ...]:
    """Modules that request the shared browser fixture, matching conftest's suite rule."""
    files: list[str] = []
    if not tests_dir.is_dir():
        return ()
    for path in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if any(argument.arg == "browser" for argument in arguments):
                files.append(f"tests/{path.name}")
                break
    return tuple(files)


def build_catalog(repo_root: Path) -> Catalog:
    conftest = repo_root / "tests" / "conftest.py"
    literals = _literal_file_sets(conftest)
    safety = tuple(f"tests/{name}" for name in literals.get("safety", FALLBACK_SAFETY))
    ui_static = tuple(f"tests/{name}" for name in literals.get("ui", FALLBACK_UI))
    return Catalog(
        ui_static=ui_static,
        safety=safety,
        browser=_browser_test_files(repo_root / "tests"),
    )


def existing_tests(repo_root: Path, tests: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    present: list[str] = []
    missing: list[str] = []
    for item in tests:
        if item == "tests" or (repo_root / item).is_file():
            present.append(item)
        else:
            missing.append(item)
    return _dedupe(present), tuple(missing)


def normalize(path: str, repo_root: Path) -> str:
    text = path.strip().strip('"')
    if not text:
        return ""
    text = text.replace("\\", "/")
    try:
        absolute = Path(text)
        if absolute.is_absolute():
            text = absolute.resolve().relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError):
        pass
    while text.startswith("./"):
        text = text[2:]
    return text


def _backend_reason(name: str, posix: str, targeted: bool = False) -> str:
    if name in {"storage.py", "auth.py", "user_paths.py"}:
        return "账户、并发与原子写入是数据安全核心，必须先跑 acceptance 回归。"
    if name.startswith("agent_") or posix.startswith("routes/agent") or posix.startswith("services/agent"):
        return "Agent 凭据与写入契约改动，跑 acceptance 回归及 Agent 检查。"
    if posix.startswith(("routes/", "services/")) or name in {"app.py", "web_common.py"}:
        return "接口与投影属于跨模块边界，跑 acceptance 回归。"
    if PLATFORM_PATTERN.match(name):
        return "平台同步、缓存与会话逻辑，跑 acceptance 回归及对应平台检查。"
    if targeted:
        return "后端行为改动，跑 acceptance 回归及该模块的专属检查。"
    return "后端行为改动，跑 acceptance 回归。"


def classify(path: str, catalog: Catalog, repo_root: Path) -> Recommendation:
    posix = normalize(path, repo_root)
    if not posix:
        return Recommendation(path, SUITE_ALL, "空路径，保守起见跑全量回归。", ("tests",))
    name = posix.rsplit("/", 1)[-1]

    # Deletions must not silently disappear from the impact map.
    if not (repo_root / posix).exists():
        return Recommendation(posix, SUITE_ALL, "删除或不存在的路径需要全量检查引用与集成。", ("tests",))

    if posix.startswith("tests/"):
        if name.startswith("test_") and posix.endswith(".py"):
            return Recommendation(posix, SUITE_DIRECT, "改动的是测试自身，直接重跑该文件即可。", (posix,))
        return Recommendation(posix, SUITE_ALL, "共享夹具或测试辅助改动影响全部用例，跑全量回归。", ("tests",))

    if posix.startswith("frontend/"):
        if posix.endswith(".css"):
            return Recommendation(posix, SUITE_DIRECT, "样式迭代先跑静态规范；交付前验证受影响的浏览器布局。", catalog.ui_static)
        elif posix.endswith(".html"):
            reason = "模板改动影响渲染结构，跑 ui 套件覆盖。"
        elif posix.endswith((".js", ".mjs")):
            reason = "前端脚本改动影响交互，跑 ui 套件（含浏览器用例）。"
        elif posix.endswith(".md"):
            reason = "设计规范文档改动随样式检查一起验证。"
        else:
            reason = "前端资源改动影响页面呈现，跑 ui 套件覆盖。"
        return Recommendation(posix, SUITE_UI, reason, catalog.files(SUITE_UI))

    if posix.startswith("scripts/"):
        tests = SCRIPT_TESTS.get(posix, SCRIPT_DEFAULT_TESTS)
        return Recommendation(
            posix, SUITE_SCRIPTS, "脚本属于开发/发布工具链，跑脚本与流程检查。", tests
        )

    if posix.startswith((".agents/", "deploy/")):
        return Recommendation(
            posix, SUITE_SCRIPTS, "部署配置与 skill 契约改动，跑部署配置检查。",
            ("tests/test_deploy_configs.py", "tests/test_scripts.py", "tests/test_development_workflow.py",
             "tests/test_release_rollback.py", "tests/test_backup_pull_workflow.py"),
        )

    if posix.startswith("skill/"):
        return Recommendation(
            posix, SUITE_SCRIPTS, "Agent Skill 与分发契约改动，跑 Agent 相关检查。",
            ("tests/test_agent_mcp.py", "tests/test_skill_endpoints.py", "tests/test_agent_api.py"),
        )

    if posix.startswith("docs/") or posix.endswith(".md"):
        return Recommendation(
            posix, SUITE_SCRIPTS, "文档与文案不改变运行行为，跑流程与配置契约检查即可。",
            ("tests/test_development_workflow.py", "tests/test_deploy_configs.py"),
        )

    if posix.startswith("requirements") or posix.startswith(".github/"):
        return Recommendation(posix, SUITE_ALL, "依赖变化影响全部用例，必须跑全量回归。", ("tests",))

    if posix == ".gitignore":
        return Recommendation(
            posix, SUITE_SCRIPTS, "忽略规则影响开发流程与打包检查。",
            ("tests/test_scripts.py", "tests/test_development_workflow.py"),
        )

    if posix == ".env.example":
        return Recommendation(
            posix, SUITE_ACCEPTANCE, "环境变量模板改动需要配置与启动检查。",
            ("tests/test_settings.py", "tests/test_deploy_configs.py"),
        )

    if posix.endswith(".py") or posix.startswith(("routes/", "services/")):
        extra = MODULE_TESTS.get(name, ())
        if extra and name not in {"storage.py", "auth.py", "user_paths.py"}:
            return Recommendation(posix, SUITE_DIRECT, "迭代先验证模块契约；交付时按影响面补充集成检查。", extra)
        return Recommendation(
            posix, SUITE_ACCEPTANCE, _backend_reason(name, posix, bool(extra)),
            catalog.files(SUITE_ACCEPTANCE) + extra,
        )

    return Recommendation(posix, SUITE_ALL, "未能归类的改动，保守起见跑全量回归。", ("tests",))


def command_for(recommendation: Recommendation) -> str:
    if recommendation.suite == SUITE_ALL:
        return r".\scripts\test.ps1"
    if recommendation.suite == SUITE_UI:
        return r".\scripts\test.ps1 -Suite ui"
    if recommendation.suite == SUITE_ACCEPTANCE:
        return r".\scripts\test.ps1 -Suite acceptance"
    tests = [test for test in recommendation.tests if test != "tests"]
    if not tests:
        return r".\scripts\test.ps1"
    if len(tests) == 1:
        return rf".\scripts\test.ps1 -PytestArgs {tests[0]}"
    joined = ",".join(f"'{test}'" for test in tests)
    return rf".\scripts\test.ps1 -PytestArgs @({joined})"


def run_git(repo_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=repo_root, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SelectionError(f"git {' '.join(arguments)} could not run: {error}") from error
    if result.returncode:
        raise SelectionError(
            f"git {' '.join(arguments)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout


def _paths(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def diff_against_parent(repo_root: Path) -> list[str]:
    """Default source: what the last commit changed."""
    try:
        return _paths(run_git(repo_root, "diff", "--name-only", "--no-renames", "HEAD~1..HEAD"))
    except SelectionError:
        # No parent commit yet: treat every tracked file as new.
        return _paths(run_git(repo_root, "ls-files"))


def diff_staged(repo_root: Path) -> list[str]:
    return _paths(run_git(repo_root, "diff", "--name-only", "--cached", "--no-renames"))


def diff_worktree(repo_root: Path) -> list[str]:
    """Uncommitted work only; a broken git query is an error, not an empty selection."""
    tracked = _paths(run_git(repo_root, "diff", "--name-only", "--no-renames", "HEAD"))
    untracked = _paths(run_git(repo_root, "ls-files", "--others", "--exclude-standard"))
    changed = list(_dedupe(tracked + untracked))
    return changed


def collect_selection(repo_root: Path, paths: list[str], catalog: Catalog) -> tuple[list[Recommendation], list[str]]:
    recommendations: list[Recommendation] = []
    notes: list[str] = []
    for path in paths:
        recommendation = classify(path, catalog, repo_root)
        present, missing = existing_tests(repo_root, recommendation.tests)
        if missing:
            notes.append(f"{recommendation.path}: skipped missing test target(s) {', '.join(missing)}")
        if not present and recommendation.suite != SUITE_ALL:
            notes.append(f"{recommendation.path}: no test target found, falls back to the full suite")
            recommendation = Recommendation(recommendation.path, SUITE_ALL, recommendation.reason, ("tests",))
            present = ("tests",)
        recommendations.append(
            Recommendation(recommendation.path, recommendation.suite, recommendation.reason, present, missing)
        )
    return recommendations, notes


def _configure_stdout() -> None:
    """Windows consoles default to a legacy code page; the reasons below are Chinese."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="Repository root (default: this checkout)")
    parser.add_argument("--files", nargs="+", metavar="PATH", help="Changed paths to classify")
    parser.add_argument("--staged", action="store_true", help="Use staged changes (git diff --cached)")
    parser.add_argument("--base", help="Include committed branch changes since the merge base, plus local changes")
    parser.add_argument("--files-from-diff", action="store_true",
                        help="Use uncommitted changes; scripts/test.ps1 -ChangedOnly calls this")
    parser.add_argument("--pytest-args", action="store_true",
                        help="Print one pytest argument per line instead of a human report")
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.files, args.staged, args.files_from_diff, args.base)) > 1:
        parser.error("choose one of --files / --staged / --files-from-diff / --base")
    repo_root = args.repo.resolve()

    try:
        if args.files:
            changed = [path for path in args.files]
        elif args.staged:
            changed = diff_staged(repo_root)
        elif args.files_from_diff:
            changed = diff_worktree(repo_root)
        elif args.base:
            base = run_git(repo_root, "merge-base", args.base, "HEAD").strip()
            changed = _paths(run_git(repo_root, "diff", "--name-only", "--no-renames", base)) + diff_worktree(repo_root)
        else:
            changed = diff_against_parent(repo_root)
    except SelectionError as error:
        print(f"Selection failed: {error}", file=sys.stderr)
        return 1

    changed = list(_dedupe(normalize(path, repo_root) for path in changed))
    catalog = build_catalog(repo_root)
    recommendations, notes = collect_selection(repo_root, changed, catalog)

    if args.pytest_args:
        for note in notes:
            print(f"note: {note}", file=sys.stderr)
        if not recommendations:
            print("no changed files; nothing to select", file=sys.stderr)
            return 0
        selected: list[str] = []
        for recommendation in recommendations:
            selected.extend(recommendation.tests)
        selected = list(_dedupe(selected))
        if "tests" in selected:
            selected = ["tests"]
        for item in selected:
            print(item)
        return 0

    print(f"Impact-based selection ({len(recommendations)} changed path(s), repo: {repo_root})")
    print()
    if not recommendations:
        print("No changed files were found; nothing to run.")
        return 0
    for recommendation in recommendations:
        print(recommendation.path)
        print(f"  suite   : {recommendation.suite}")
        print(f"  reason  : {recommendation.reason}")
        print(f"  command : {command_for(recommendation)}")
        print()
    by_command: dict[str, int] = {}
    for recommendation in recommendations:
        command = command_for(recommendation)
        order = SUITE_ORDER.get(recommendation.suite, SUITE_ORDER[SUITE_SCRIPTS])
        if command not in by_command or order < by_command[command]:
            by_command[command] = order
    ordered = [item[0] for item in sorted(by_command.items(), key=lambda item: (item[1], item[0]))]
    print("Recommended commands (deduplicated, cheapest first):")
    for command in ordered:
        print(f"  {command}")
    print(r"Before release: run the full regression .\scripts\test.ps1")
    if notes:
        print()
        for note in notes:
            print(f"note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
