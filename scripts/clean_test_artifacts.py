"""Rotate ignored test evidence under test-results/ and report empty pytest temp leftovers.

Dry-run by default: nothing is deleted unless --apply is passed. A run directory is only ever
removed when it resolves directly below this repository's ``test-results/``, its name matches the
run id pattern ``<yyyymmdd-HHMMSS-8 hex>`` and it is not a link or reparse point. The newest run is
always kept; up to --keep-success passing runs and --keep-failed failing (or unreadable) runs are
kept as well, so failures stay available as evidence.

Repository-root ``.pytest-tmp-*`` / ``.codex-pytest-*`` leftovers (both are git-ignored) are
reported, and only removed with --apply when they contain no file at any depth.

Standard library only:

    .\\.venv\\Scripts\\python.exe scripts/clean_test_artifacts.py --keep-success 10 --keep-failed 30
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")
RESIDUE_PATTERN = re.compile(r"^\.(?:pytest-tmp|codex-pytest)-")
FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass
class RunRecord:
    """One test-results/<run-id>/ directory and the evidence it carries."""

    name: str
    path: Path
    exit_code: int | None
    suite: str
    collection_only: bool
    evidence_error: str
    size: int

    @property
    def failed(self) -> bool:
        return self.exit_code is not None and self.exit_code != 0

    @property
    def unknown(self) -> bool:
        return self.exit_code is None

    @property
    def status(self) -> str:
        if self.unknown:
            return "unknown"
        return "fail" if self.failed else "pass"

    @property
    def detail(self) -> str:
        if self.unknown:
            return self.evidence_error
        return f"exit={self.exit_code} suite={self.suite}"


def is_reparse_point(entry: os.DirEntry[str]) -> bool:
    """True for symlinks and Windows junction/reparse points, which must never be deleted."""
    if entry.is_symlink():
        return True
    try:
        attributes = entry.stat(follow_symlinks=False).st_file_attributes  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def directory_size(path: Path) -> int:
    total = 0
    for current, _dirnames, filenames in os.walk(path, followlinks=False, onerror=lambda _error: None):
        for filename in filenames:
            try:
                total += os.stat(os.path.join(current, filename), follow_symlinks=False).st_size
            except OSError:
                continue
    return total


def read_run(path: Path) -> tuple[int | None, str, bool, str]:
    """Return (exit_code, suite, collection_only, evidence_error) for one run directory."""
    metadata = path / "run.json"
    if not metadata.is_file():
        return None, "-", False, "run.json is missing"
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return None, "-", False, f"run.json is unreadable: {type(error).__name__}"
    if not isinstance(payload, dict):
        return None, "-", False, "run.json is not an object"
    exit_code = payload.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return None, str(payload.get("suite") or "-"), False, "run.json has no integer exit_code"
    return (
        exit_code,
        str(payload.get("suite") or "-"),
        bool(payload.get("collection_only")),
        "",
    )


def scan_runs(runs_root: Path, *, measure_size: bool = True) -> tuple[list[RunRecord], list[tuple[str, str]]]:
    """Collect valid run directories; the second list reports entries that are left alone."""
    records: list[RunRecord] = []
    skipped: list[tuple[str, str]] = []
    if not runs_root.is_dir():
        return records, skipped
    with os.scandir(runs_root) as entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if not RUN_ID_PATTERN.match(entry.name):
                skipped.append((entry.name, "name does not match <yyyymmdd-HHMMSS-8hex>"))
                continue
            if is_reparse_point(entry):
                skipped.append((entry.name, "link or reparse point"))
                continue
            path = Path(entry.path)
            exit_code, suite, collection_only, error = read_run(path)
            records.append(
                RunRecord(
                    name=entry.name,
                    path=path,
                    exit_code=exit_code,
                    suite=suite,
                    collection_only=collection_only,
                    evidence_error=error,
                    size=directory_size(path) if measure_size else 0,
                )
            )
    records.sort(key=lambda record: record.name, reverse=True)
    return records, skipped


def plan_runs(
    records: list[RunRecord], keep_success: int, keep_failed: int
) -> tuple[list[tuple[RunRecord, str]], list[RunRecord]]:
    """Mirror scripts/test.ps1 retention: newest run kept, then the newest N per outcome."""
    kept: list[tuple[RunRecord, str]] = []
    removed: list[RunRecord] = []
    passing = 0
    failing = 0
    for index, record in enumerate(records):
        if index == 0:
            kept.append((record, "newest run, always kept"))
            continue
        if record.unknown:
            kept.append((record, "unreadable evidence, always kept"))
            continue
        if record.failed:
            failing += 1
            if failing <= keep_failed:
                kept.append((record, f"failing #{failing} within --keep-failed {keep_failed}"))
            else:
                removed.append(record)
        else:
            passing += 1
            if passing <= keep_success:
                kept.append((record, f"passing #{passing} within --keep-success {keep_success}"))
            else:
                removed.append(record)
    return kept, removed


def validate_run_directory(repo_root: Path, path: Path) -> str:
    """Re-check every precondition immediately before deletion; "" means safe to remove."""
    runs_root = (repo_root / "test-results").resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return "directory disappeared"
    if resolved.parent != runs_root:
        return "not a direct child of test-results/"
    if not RUN_ID_PATTERN.match(path.name):
        return "name does not match <yyyymmdd-HHMMSS-8hex>"
    if path.is_symlink():
        return "link or reparse point"
    if not path.is_dir():
        return "not a directory"
    return ""


def scan_residue(repo_root: Path) -> list[tuple[Path, int, int, int]]:
    """Return (path, files, directories, bytes) for root-level pytest temp leftovers."""
    results: list[tuple[Path, int, int, int]] = []
    with os.scandir(repo_root) as entries:
        for entry in entries:
            if not RESIDUE_PATTERN.match(entry.name) or not entry.is_dir(follow_symlinks=False):
                continue
            files = 0
            directories = 0
            size = 0
            for current, dirnames, filenames in os.walk(
                entry.path, followlinks=False, onerror=lambda _error: None
            ):
                files += len(filenames)
                directories += len(dirnames)
                for filename in filenames:
                    try:
                        size += os.stat(os.path.join(current, filename), follow_symlinks=False).st_size
                    except OSError:
                        continue
            results.append((Path(entry.path), files, directories, size))
    results.sort(key=lambda item: item[0].name)
    return results


def remove_directory(path: Path) -> str:
    """Delete a directory tree, clearing the read-only bit once if Windows blocks it."""

    def on_error(function, target, _exc_info):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError as error:
            raise OSError(f"{target}: {error}") from error

    try:
        shutil.rmtree(path, onerror=on_error)
    except OSError as error:
        return f"{type(error).__name__}: {error}"
    return "" if not path.exists() else "directory still exists after removal"


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"  # pragma: no cover - unreachable


def rotate_runs(repo_root: Path, current_run: str, keep_success: int, keep_failed: int) -> int:
    """Fast automatic retention: metadata only, same safety checks as manual cleanup."""
    records, _ = scan_runs(repo_root / "test-results", measure_size=False)
    _, candidates = plan_runs(records, keep_success, keep_failed)
    removed = 0
    for record in candidates:
        if record.name == current_run:
            continue
        problem = validate_run_directory(repo_root, record.path)
        if problem:
            print(f"Retention skipped {record.name}: {problem}")
            continue
        error = remove_directory(record.path)
        if error:
            print(f"Retention skipped {record.name}: {error}")
        else:
            removed += 1
    print(f"Artifact retention: removed {removed} old recorded run(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="Repository root (default: this checkout)")
    parser.add_argument("--keep-success", type=int, default=10, metavar="N",
                        help="Newest passing runs to keep (default: 10)")
    parser.add_argument("--keep-failed", type=int, default=30, metavar="N",
                        help="Newest failing or unreadable runs to keep (default: 30)")
    parser.add_argument("--apply", action="store_true", help="Actually delete; default is a dry run")
    parser.add_argument("--current-run", help="With --apply, run metadata-only automatic retention and protect this run")
    parser.add_argument("--verbose", action="store_true",
                        help="List every deletion candidate instead of the newest 20")
    parser.add_argument("--skip-residue", action="store_true",
                        help="Do not report or clean .pytest-tmp-* / .codex-pytest-* leftovers")
    args = parser.parse_args(argv)
    if args.keep_success < 0 or args.keep_failed < 0:
        parser.error("--keep-success and --keep-failed must be zero or greater")
    repo_root = args.repo.resolve()
    runs_root = repo_root / "test-results"
    if args.current_run:
        if not args.apply or not RUN_ID_PATTERN.fullmatch(args.current_run):
            parser.error("--current-run requires --apply and a valid run ID")
        return rotate_runs(repo_root, args.current_run, args.keep_success, args.keep_failed)

    print("Canvas Dashboard test artifacts")
    print(f"repository : {repo_root}")
    print(f"runs root  : {runs_root}")
    print(f"mode       : {'APPLY (entries marked DELETE are removed)' if args.apply else 'DRY RUN (nothing is deleted)'}")
    print(f"keep       : --keep-success {args.keep_success}, --keep-failed {args.keep_failed}, newest run always kept")
    print()

    records, skipped = scan_runs(runs_root)
    kept, removed = plan_runs(records, args.keep_success, args.keep_failed)

    for record, reason in kept:
        print(f"KEEP    {record.status:<7} {record.name}  {record.detail}  [{reason}]")
    listing = removed if args.verbose else removed[:20]
    for record in listing:
        print(f"DELETE  {record.status:<7} {record.name}  {record.detail}  [{human_size(record.size)}]")
    if len(removed) > len(listing):
        print(f"DELETE  ... {len(removed) - len(listing)} more run(s) "
              f"({human_size(sum(record.size for record in removed[len(listing):]))}); use --verbose to list them")
    for name, reason in skipped:
        print(f"SKIP             {name}  [{reason}]")

    reclaimable = sum(record.size for record in removed)
    print()
    print(f"runs       : {len(records)} scanned, {len(kept)} kept, {len(removed)} to delete"
          f" ({human_size(reclaimable)} reclaimable)")

    residue_items: list[tuple[Path, int, int, int]] = []
    residue_removed: list[Path] = []
    residue_skipped: list[tuple[Path, int]] = []
    if not args.skip_residue:
        for path, files, directories, size in scan_residue(repo_root):
            if files == 0:
                residue_items.append((path, files, directories, size))
                residue_removed.append(path)
            else:
                residue_skipped.append((path, files))
        print(f"residue    : {len(residue_removed)} empty, {len(residue_skipped)} non-empty"
              " (.pytest-tmp-* / .codex-pytest-* at the repository root)")
        for path, _files, directories, size in residue_items:
            suffix = f", {directories} empty subdirectories" if directories else ""
            print(f"DELETE  residue  {path.name}  [no files{suffix}, {human_size(size)}]")
        for path, files in residue_skipped:
            print(f"SKIP    residue  {path.name}  [contains {files} file(s)]")

    if not args.apply:
        print()
        print(f"DRY RUN: nothing deleted. Re-run with --apply to remove "
              f"{len(removed) + len(residue_removed)} entry/entries and free {human_size(reclaimable)}.")
        return 0

    print()
    failures = 0
    deleted_runs = 0
    deleted_residue = 0
    freed = 0
    for record in removed:
        problem = validate_run_directory(repo_root, record.path)
        if problem:
            print(f"REFUSED {record.name}: {problem}")
            failures += 1
            continue
        error = remove_directory(record.path)
        if error:
            print(f"FAILED  {record.name}: {error}")
            failures += 1
        else:
            deleted_runs += 1
            freed += record.size
    for path in residue_removed:
        if path.resolve().parent != repo_root or not RESIDUE_PATTERN.match(path.name):
            print(f"REFUSED {path.name}: not a repository-root pytest temp directory")
            failures += 1
            continue
        error = remove_directory(path)
        if error:
            print(f"FAILED  {path.name}: {error}")
            failures += 1
        else:
            deleted_residue += 1
    print(f"deleted    : {deleted_runs} run(s), {deleted_residue} residue directory/ies, "
          f"{human_size(freed)} from runs")
    if failures:
        print(f"errors     : {failures} entry/entries could not be removed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
