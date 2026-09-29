"""Read-only release guard: deploy the clean, pushed main commit that was tested."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

EVIDENCE_ROOT = "test-results"
FULL_SUITE = "all"


def git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"git {args[0]} could not finish: {error}") from error
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def check_release(repo: Path, expected: str | None = None) -> str:
    if git(repo, "branch", "--show-current") != "main":
        raise RuntimeError("Release requires the main branch after local acceptance and merge.")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("Release requires a clean working tree, including untracked source files.")
    commit = git(repo, "rev-parse", "HEAD")
    if expected and commit != expected:
        raise RuntimeError("HEAD changed after validation; rerun the release checks.")
    remote = git(repo, "ls-remote", "--exit-code", "origin", "refs/heads/main").split()
    if not remote or remote[0] != commit:
        raise RuntimeError("HEAD differs from origin main. Push main successfully before deploying.")
    return commit


def _local_name(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _declared_totals(root: ElementTree.Element, suites: list[ElementTree.Element]) -> tuple[dict[str, int] | None, list[str]]:
    """Read tests/failures/errors totals, refusing anything that cannot be read completely."""
    names = ("tests", "failures", "errors")
    problems: list[str] = []

    def read_totals(element: ElementTree.Element) -> dict[str, int] | None:
        if not any(element.get(name) is not None for name in names):
            return None
        values: dict[str, int] = {}
        for name in names:
            raw = element.get(name)
            if raw is None:
                problems.append(f"results.xml <{_local_name(element.tag)}> is missing its {name} count")
                return None
            try:
                values[name] = int(raw)
            except ValueError:
                problems.append(f"results.xml <{_local_name(element.tag)}> has a non-numeric {name} count ({raw!r})")
                return None
        return values

    root_totals = read_totals(root)
    suite_totals = None
    if suites:
        per_suite = [read_totals(suite) for suite in suites]
        if any(item is not None for item in per_suite):
            if all(item is not None for item in per_suite):
                suite_totals = {name: sum(item[name] for item in per_suite if item) for name in names}
            else:
                problems.append("results.xml declares incomplete per-suite totals")
    if root_totals is None and suite_totals is None:
        problems.append("results.xml declares no usable test totals")
    return (root_totals if root_totals is not None else suite_totals), problems


def junit_failures(results_path: Path) -> list[str]:
    """Return every reason this JUnit report does not prove a complete, failure-free run."""
    try:
        root = ElementTree.parse(results_path).getroot()
    except (OSError, ElementTree.ParseError) as error:
        return [f"results.xml could not be parsed: {error}"]
    if _local_name(root.tag) not in ("testsuites", "testsuite"):
        return [f"results.xml is not a JUnit report (root element {_local_name(root.tag)!r})"]
    testcases = [node for node in root.iter() if _local_name(node.tag) == "testcase"]
    suites = [node for node in root.iter() if _local_name(node.tag) == "testsuite"]
    problems: list[str] = []
    if not testcases:
        problems.append("results.xml contains no test case elements")
    observed = {
        "failures": sum(1 for case in testcases if any(_local_name(child.tag) == "failure" for child in case)),
        "errors": sum(1 for case in testcases if any(_local_name(child.tag) == "error" for child in case)),
    }
    totals, total_problems = _declared_totals(root, suites)
    problems.extend(total_problems)
    if totals is not None:
        if totals["tests"] != len(testcases):
            problems.append(
                f"results.xml reports {totals['tests']} tests but contains {len(testcases)} test case elements")
        for name in ("failures", "errors"):
            if totals[name] or observed[name]:
                problems.append(
                    f"results.xml reports {totals[name]} {name} and {observed[name]} <{name[:-1]}> elements")
            elif totals[name] != observed[name]:
                problems.append(f"results.xml {name} totals disagree with its test case elements")
    return problems


def read_manifest(run_dir: Path) -> tuple[object, list[str]]:
    """Return the run.json document and, when it cannot be read, the reason."""
    try:
        # scripts/test.ps1 writes run.json with Windows PowerShell Set-Content -Encoding UTF8, which adds a BOM.
        return json.loads((run_dir / "run.json").read_text(encoding="utf-8-sig")), []
    except OSError as error:
        return None, [f"run.json could not be read: {error}"]
    except ValueError as error:
        return None, [f"run.json is not valid JSON: {error}"]


def manifest_failures(manifest: object, commit: str) -> list[str]:
    """Return every reason a run.json document does not describe a clean, passing full suite of commit."""
    if not isinstance(manifest, dict):
        return ["run.json does not contain a JSON object"]
    problems: list[str] = []
    recorded = manifest.get("commit")
    if not isinstance(recorded, str) or not recorded:
        problems.append("run.json records no commit")
    elif recorded != commit:
        problems.append(f"run.json records commit {recorded}, not the release commit {commit}")
    if manifest.get("suite") != FULL_SUITE:
        problems.append(f"run.json suite is {manifest.get('suite')!r}, not {FULL_SUITE!r}")
    if manifest.get("dirty") is not False:
        problems.append(f"run.json dirty is {manifest.get('dirty')!r}, not false")
    exit_code = manifest.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        problems.append(f"run.json exit_code is {exit_code!r}, not an integer")
    elif exit_code != 0:
        problems.append(f"run.json exit_code is {exit_code}, not 0")
    if manifest.get("collection_only") is not False:
        problems.append(f"run.json collection_only is {manifest.get('collection_only')!r}, not false")
    return problems


def artifact_failures(run_dir: Path) -> list[str]:
    """Return every reason the recorded JUnit report or pytest log is missing, unreadable or failing."""
    problems: list[str] = []
    results_path = run_dir / "results.xml"
    if not results_path.is_file():
        problems.append("results.xml is missing")
    else:
        problems.extend(junit_failures(results_path))
    log_path = run_dir / "pytest.log"
    if not log_path.is_file():
        problems.append("pytest.log is missing")
    else:
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            problems.append(f"pytest.log could not be read: {error}")
        else:
            if not log_text.lstrip("\ufeff").strip():
                problems.append("pytest.log is empty")
    return problems


def inspect_run(run_dir: Path, commit: str) -> tuple[list[str], bool]:
    """Return (reasons this run directory is not acceptable evidence, whether run.json claims a
    full-suite run of commit). The second value only classifies rejected runs for reporting."""
    manifest, problems = read_manifest(run_dir)
    is_full_suite = (isinstance(manifest, dict) and manifest.get("commit") == commit
                     and manifest.get("suite") == FULL_SUITE)
    return (list(problems) + manifest_failures(manifest, commit) + artifact_failures(run_dir), is_full_suite)


def check_test_evidence(repo: Path, expected: str | None = None) -> str:
    """Return the commit only when recorded evidence proves that exact revision passed the full suite."""
    commit = check_release(repo, expected)
    evidence_root = repo / EVIDENCE_ROOT
    if not evidence_root.is_dir():
        raise RuntimeError(
            f"No {EVIDENCE_ROOT} directory records a full-suite run of {commit}; "
            f"run scripts/test.ps1 -Suite all before skipping the local regression.")
    manifests = sorted(
        (path for path in evidence_root.glob("*/run.json") if path.is_file()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    if not manifests:
        raise RuntimeError(
            f"No {EVIDENCE_ROOT}/*/run.json records a full-suite run of {commit}; "
            f"run scripts/test.ps1 -Suite all before skipping the local regression.")
    rejected: list[tuple[Path, list[str], bool]] = []
    for manifest_path in manifests:
        run_dir = manifest_path.parent
        problems, is_full_suite = inspect_run(run_dir, commit)
        if not problems:
            print(f"Accepted test evidence: {run_dir.relative_to(repo)} (clean full suite of {commit}).",
                  file=sys.stderr)
            newer = [path for path, _, full_suite in rejected if full_suite]
            if newer:
                print(f"Warning: {len(newer)} newer recorded full-suite run(s) of this commit were rejected "
                      f"({', '.join(path.name for path in newer[:3])}); inspect them before trusting this evidence.",
                      file=sys.stderr)
            return commit
        rejected.append((run_dir, problems, is_full_suite))
    detail = "\n".join(
        f"  - {run_dir.relative_to(repo)}: " + "; ".join(problems) for run_dir, problems, _ in rejected[:5])
    raise RuntimeError(
        f"No recorded full-suite run proves {commit} passed "
        f"({len(rejected)} run(s) examined, newest first):\n{detail}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected")
    parser.add_argument(
        "--test-evidence",
        action="store_true",
        help="require a clean, pushed, recorded full-suite pass for this exact commit instead of trusting a rerun",
    )
    args = parser.parse_args()
    try:
        repo_root = Path(__file__).resolve().parents[1]
        if args.test_evidence:
            commit = check_test_evidence(repo_root, args.expected)
        else:
            commit = check_release(repo_root, args.expected)
        print(commit)
    except RuntimeError as error:
        parser.exit(1, f"Release blocked: {error}\n")
