"""Read-only release guard: deploy the clean, pushed main commit that was tested."""
import argparse
from pathlib import Path
import subprocess


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected")
    args = parser.parse_args()
    try:
        print(check_release(Path(__file__).resolve().parents[1], args.expected))
    except RuntimeError as error:
        parser.exit(1, f"Release blocked: {error}\n")
