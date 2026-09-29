"""Diagnose whether this machine can run the repository test suite.

Prints the interpreter in use, the TEMP/TMP directories a test run inherits, the
``CANVAS_TEST_ARTIFACTS`` target, module availability (flask / pytest / pytest-xdist /
playwright) and whether ``tempfile.TemporaryDirectory`` can still be cleaned up here.

Exit code 0 means the suite can run locally; 1 means something must be fixed first, for
example TEMP living in a directory this sandbox cannot delete - ``tests/conftest.py``
cleans its session temp directory at teardown and raises ``PermissionError`` there.

Standard library only, read-only apart from one probe file/directory that is removed
again. Run it with either interpreter:

    .\\.venv\\Scripts\\python.exe scripts/check_test_env.py
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib.util
import os
import platform
from pathlib import Path
import re
import shutil
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = REPO_ROOT / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
REQUIRED_MODULES = ("flask", "pytest")
WORKER_DEFAULT = 4
RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")
RESIDUE_PATTERN = re.compile(r"^\.(?:pytest-tmp|codex-pytest)-")
PROBE_PREFIX = "canvas-dashboard-envcheck-"


@dataclass
class Finding:
    """One diagnosis line: OK/INFO never fail the run, WARN is advisory, FAIL exits 1."""

    level: str
    title: str
    detail: list[str] = field(default_factory=list)
    advice: str = ""

    def render(self) -> str:
        lines = [f"[{self.level}] {self.title}"]
        lines.extend(f"       {line}" for line in self.detail)
        if self.advice:
            lines.append(f"       -> {self.advice}")
        return "\n".join(lines)


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def module_version(name: str) -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(name)
        except PackageNotFoundError:
            return None
    except Exception:  # pragma: no cover - metadata is best effort only
        return None


def probe_write(directory: Path) -> str:
    """Create and remove one probe file; return "" on success, else the reason."""
    probe = directory / f".{PROBE_PREFIX}{os.getpid()}"
    try:
        probe.write_text("probe", encoding="utf-8")
    except OSError as error:
        return f"{type(error).__name__}: {error}"
    try:
        probe.unlink()
    except OSError as error:
        return f"file was written but cannot be removed: {type(error).__name__}: {error}"
    return ""


def same_directory(left: Path, right: Path) -> bool:
    """Compare two directories even when one is spelled with a short (8.3) Windows name."""
    try:
        if left.exists() and right.exists():
            return os.path.samefile(left, right)
    except OSError:
        pass
    return os.path.normcase(str(left)).rstrip("\\/") == os.path.normcase(str(right)).rstrip("\\/")


def same_as_repo_venv() -> bool:
    if not VENV_PYTHON.exists() or not sys.executable:
        return False
    try:
        return os.path.samefile(sys.executable, VENV_PYTHON)
    except OSError:
        return Path(sys.executable).resolve() == VENV_PYTHON.resolve()


def check_interpreter() -> Finding:
    missing = [name for name in REQUIRED_MODULES if not module_available(name)]
    available = [
        "{}={}".format(name, "yes" if module_available(name) else "no") for name in REQUIRED_MODULES
    ]
    detail = [
        f"sys.executable  : {sys.executable}",
        f"version         : {platform.python_version()} ({platform.system()} {platform.machine()})",
        f"repo venv       : {VENV_PYTHON} [{'present' if VENV_PYTHON.exists() else 'missing'}]",
        f"required modules: {', '.join(available)}",
    ]
    if missing:
        return Finding(
            "FAIL",
            f"the current interpreter cannot run the tests (missing: {', '.join(missing)})",
            detail,
            r"use the pinned environment: .\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest",
        )
    if not VENV_PYTHON.exists():
        return Finding(
            "FAIL",
            "the repository virtual environment is missing",
            detail,
            "create it with: py -m venv .venv  (scripts/test.ps1 always runs .venv\\Scripts\\python.exe)",
        )
    if not same_as_repo_venv():
        return Finding(
            "WARN",
            "running under an interpreter that is not the repository .venv",
            detail,
            r"prefer .\.venv\Scripts\python.exe for direct pytest runs; scripts\test.ps1 pins it for you",
        )
    return Finding("OK", "interpreter and test dependencies are usable", detail)


def check_encoding() -> Finding:
    value = os.environ.get("PYTHONUTF8")
    detail = [f"PYTHONUTF8     : {value or '(unset)'}"]
    if value == "1":
        return Finding("OK", "UTF-8 mode is enabled", detail)
    return Finding(
        "WARN",
        "PYTHONUTF8 is not set",
        detail,
        r"scripts\test.ps1 sets PYTHONUTF8=1; export it as well when running pytest directly on Windows",
    )


def check_temp() -> Finding:
    configured = {name: os.environ.get(name) for name in ("TEMP", "TMP", "TMPDIR")}
    detail = [f"{name:<15}: {value or '(unset)'}" for name, value in configured.items()]
    try:
        effective = Path(tempfile.gettempdir())
    except OSError as error:
        return Finding(
            "FAIL",
            "Python found no usable temporary directory",
            detail + [f"raised          : {type(error).__name__}: {error}"],
            "point TEMP and TMP at an existing writable directory before running the tests",
        )
    detail.append(f"{'gettempdir()':<15}: {effective}")
    if not effective.is_dir():
        return Finding(
            "FAIL",
            "the effective temporary directory does not exist",
            detail,
            "point TEMP and TMP at an existing writable directory before running the tests",
        )
    error = probe_write(effective)
    if error:
        return Finding(
            "FAIL",
            "the effective temporary directory is not writable",
            detail + [f"probe failed   : {error}"],
            "point TEMP and TMP at a writable directory (scripts/test.ps1 creates its own under the "
            "system temp root), then rerun this check",
        )
    ignored = [
        name
        for name, value in configured.items()
        if value and not same_directory(Path(value), effective)
    ]
    if ignored:
        return Finding(
            "FAIL",
            f"{', '.join(ignored)} cannot be used, so Python silently falls back to {effective}",
            detail,
            "a TEMP that cannot be created or deleted is what leaves .pytest-tmp-* / .codex-pytest-* "
            "residue inside the repository; point TEMP/TMP at a writable directory (scripts/test.ps1 "
            "sets both to its own temp root) or unset them",
        )
    inside_repo = False
    try:
        inside_repo = effective.resolve().is_relative_to(REPO_ROOT.resolve())
    except OSError:
        inside_repo = False
    if inside_repo:
        return Finding(
            "WARN",
            "TEMP/TMP resolve inside the repository",
            detail,
            "leftovers such as .pytest-tmp-* / .codex-pytest-* slow down rg/glob; keep TEMP outside the "
            "repo or clean it with scripts/clean_test_artifacts.py",
        )
    return Finding("OK", "TEMP/TMP are writable and outside the repository", detail)


def check_temporary_directory() -> Finding:
    """Mirror tests/conftest.py: create a nested tree, then delete it at teardown."""
    created = tempfile.TemporaryDirectory(prefix=PROBE_PREFIX)
    root = Path(created.name)
    detail = [f"probe           : {root}"]
    failure: BaseException | None = None
    try:
        nested = root / "data" / "users"
        nested.mkdir(parents=True)
        (nested / "probe.json").write_text("{}", encoding="utf-8")
        created.cleanup()
    except Exception as error:  # noqa: BLE001 - any sandbox error is the diagnosis
        failure = error
    leftover = root.exists()
    if leftover:
        detail.append("leftover        : directory still exists after cleanup")
        try:
            shutil.rmtree(root, ignore_errors=True)
        except Exception:  # pragma: no cover - best effort cleanup only
            pass
    if failure is not None:
        detail.append(f"raised          : {type(failure).__name__}: {failure}")
        return Finding(
            "FAIL",
            "tempfile.TemporaryDirectory cannot be cleaned up here",
            detail,
            "tests/conftest.py cleans its session temp directory at teardown and will fail the same way; "
            "make the temp root writable for this account (or run under a sandbox that allows deleting it), "
            "then rerun this check",
        )
    if leftover:
        return Finding(
            "FAIL",
            "tempfile.TemporaryDirectory was not removed completely",
            detail,
            "check the ACLs of the temp root; a leftover tree breaks pytest runs and repo search tools",
        )
    return Finding("OK", "tempfile.TemporaryDirectory can be created and cleaned up", detail)


def check_artifacts() -> Finding:
    value = os.environ.get("CANVAS_TEST_ARTIFACTS")
    if not value:
        return Finding(
            "INFO",
            "CANVAS_TEST_ARTIFACTS is not set",
            ["artifacts       : (unset)"],
            r"normal outside scripts\test.ps1, which points it at test-results\<run-id>",
        )
    target = Path(value)
    detail = [f"artifacts       : {target}"]
    if not target.is_absolute():
        return Finding(
            "FAIL",
            "CANVAS_TEST_ARTIFACTS is not an absolute path",
            detail,
            "unset it or set an absolute directory; scripts/test.ps1 always writes an absolute path",
        )
    if target.exists():
        if not target.is_dir():
            return Finding("FAIL", "CANVAS_TEST_ARTIFACTS is not a directory", detail,
                           "point it at a directory or unset it")
        error = probe_write(target)
        if error:
            return Finding(
                "FAIL",
                "CANVAS_TEST_ARTIFACTS is not writable",
                detail + [f"probe failed   : {error}"],
                "unset it or point it at a writable directory",
            )
        return Finding("OK", "CANVAS_TEST_ARTIFACTS is a writable directory", detail)
    parent = target.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    error = probe_write(parent)
    if error:
        return Finding(
            "FAIL",
            "CANVAS_TEST_ARTIFACTS cannot be created",
            detail + [f"nearest parent : {parent}", f"probe failed   : {error}"],
            "unset it or point it at a writable directory",
        )
    return Finding("OK", "CANVAS_TEST_ARTIFACTS does not exist yet and can be created", detail)


def check_parallelism() -> Finding:
    xdist = module_available("xdist")
    workers = os.environ.get("CANVAS_TEST_WORKERS") or str(WORKER_DEFAULT)
    pytest_version = module_version("pytest") or "unknown"
    detail = [
        f"pytest         : {pytest_version}",
        f"pytest-xdist   : {module_version('pytest-xdist') if xdist else 'missing'}",
        f"requested -n   : CANVAS_TEST_WORKERS={os.environ.get('CANVAS_TEST_WORKERS') or '(unset)'}"
        f" -> default {workers}",
    ]
    if xdist:
        return Finding(
            "OK",
            "pytest-xdist is available for parallel runs",
            detail + [r"scripts\test.ps1 runs -n <workers> --dist loadfile; -List forces 1 worker"],
        )
    return Finding(
        "WARN",
        "pytest-xdist is missing, so tests would fall back to serial",
        detail,
        r"install it with: .\.venv\Scripts\python.exe -m pip install pytest-xdist",
    )


def check_playwright() -> Finding:
    available = module_available("playwright")
    detail = [f"playwright     : {module_version('playwright') if available else 'missing'}"]
    if available:
        return Finding("OK", "playwright is importable (browser suites can run)", detail)
    return Finding(
        "WARN",
        "playwright is missing, so the ui and acceptance suites cannot run",
        detail,
        r"install it with: .\.venv\Scripts\python.exe -m pip install -r requirements.txt "
        r"&& .\.venv\Scripts\python.exe -m playwright install chromium",
    )


def check_workspace_hygiene() -> Finding:
    residue: list[Path] = []
    try:
        for entry in os.scandir(REPO_ROOT):
            if entry.is_dir(follow_symlinks=False) and RESIDUE_PATTERN.match(entry.name):
                residue.append(Path(entry.path))
    except OSError:
        pass
    runs_root = REPO_ROOT / "test-results"
    runs = 0
    if runs_root.is_dir():
        try:
            runs = sum(
                1
                for entry in os.scandir(runs_root)
                if entry.is_dir(follow_symlinks=False) and RUN_ID_PATTERN.match(entry.name)
            )
        except OSError:
            runs = 0
    detail = [
        f"residue dirs   : {len(residue)} (.pytest-tmp-* / .codex-pytest-* at the repo root)",
        f"test-results   : {runs} recorded run(s)",
    ]
    if not residue and runs <= 30:
        return Finding("INFO", "workspace hygiene looks fine", detail)
    return Finding(
        "INFO",
        "workspace hygiene can be improved",
        detail,
        r"scripts/clean_test_artifacts.py --keep-success 10 --keep-failed 30 (dry-run; add --apply to delete)",
    )


def collect_findings() -> list[Finding]:
    return [
        check_interpreter(),
        check_encoding(),
        check_temp(),
        check_temporary_directory(),
        check_artifacts(),
        check_parallelism(),
        check_playwright(),
        check_workspace_hygiene(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.parse_args(argv)
    print("Canvas Dashboard test environment")
    print(f"repository      : {REPO_ROOT}")
    print()
    findings = collect_findings()
    for finding in findings:
        print(finding.render())
        print()
    failures = [finding for finding in findings if finding.level == "FAIL"]
    warnings = [finding for finding in findings if finding.level == "WARN"]
    if failures:
        print(f"Verdict: MUST FIX - {len(failures)} blocking problem(s), {len(warnings)} warning(s).")
        return 1
    print(f"Verdict: READY - 0 blocking problems, {len(warnings)} warning(s).")
    print(r"Run the suite with .\scripts\test.ps1 (full), -Suite quick, -Suite ui or -Suite acceptance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
