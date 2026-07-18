"""Background worker for keeping Zhihuishu data cached outside Flask requests."""
import argparse
import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import settings
import zhihuishu_store

KEEPALIVE_INTERVAL_SECONDS = settings.ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS
FETCH_INTERVAL_SECONDS = settings.ZHIHUISHU_FETCH_INTERVAL_SECONDS
MAX_FAILURE_DELAY_SECONDS = settings.ZHIHUISHU_MAX_FAILURE_DELAY_SECONDS
FETCH_TIMEOUT_SECONDS = settings.ZHIHUISHU_FETCH_TIMEOUT_SECONDS

LOCK_FILE = Path(__file__).parent / "data" / "zhihuishu_worker.lock"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [zhihuishu-worker] %(levelname)s: %(message)s")
logger = logging.getLogger("zhihuishu_worker")


def next_delay_seconds(failure_count: int) -> int:
    return min(KEEPALIVE_INTERVAL_SECONDS * (2 ** max(0, failure_count)), MAX_FAILURE_DELAY_SECONDS)


@contextmanager
def single_instance_lock():
    try:
        import fcntl
    except ImportError as exc:
        raise RuntimeError("zhihuishu_worker single-instance lock requires fcntl on Ubuntu/Linux") from exc

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("another zhihuishu_worker instance is already running") from exc
        lock_file.write(str(time.time()))
        lock_file.flush()
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _all_usernames() -> list[str]:
    users_dir = zhihuishu_store.DATA_DIR / "users"
    if not users_dir.exists():
        return []
    return sorted(path.name for path in users_dir.iterdir() if path.is_dir())


def _browser_module():
    browser = globals().get("zhihuishu_browser")
    if browser is not None:
        return browser
    import zhihuishu_browser as browser
    return browser


def run_scheduled_cycle(username: str, now: float | None = None, force_fetch: bool = False) -> bool:
    now = now or time.time()
    status = zhihuishu_store.load_status(username)
    browser = _browser_module()

    if not browser.check_session(username):
        zhihuishu_store.save_status(username, {
            "session": "need_relogin",
            "worker": "running",
            "last_error": "智慧树登录态失效",
        })
        return False

    browser.keepalive(username)
    updates = {
        "session": "active",
        "worker": "running",
        "last_keepalive_at": now,
        "last_error": "",
    }

    last_fetch_at = status.get("last_fetch_at")
    should_fetch = force_fetch or not last_fetch_at or (now - float(last_fetch_at)) >= FETCH_INTERVAL_SECONDS
    if should_fetch:
        items = browser.fetch_assignments(username)
        zhihuishu_store.save_cache(username, items, fetched_at=now)
        updates["last_fetch_at"] = now
        updates["last_success_at"] = now

    zhihuishu_store.save_status(username, updates)
    return True


def _run_once(username: str, dry_run: bool = False) -> bool:
    now = time.time()
    if dry_run:
        zhihuishu_store.save_status(username, {
            "worker": "dry_run",
            "last_keepalive_at": now,
            "last_error": "",
        })
        return True

    return run_scheduled_cycle(username, now=now, force_fetch=True)


def _run_user_subprocess(username: str, dry_run: bool = False) -> bool:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--username",
        username,
        "--once",
        "--child-cycle",
    ]
    if dry_run:
        command.append("--dry-run")
    try:
        result = subprocess.run(
            command,
            timeout=FETCH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        message = f"worker cycle timed out after {FETCH_TIMEOUT_SECONDS} seconds"
        zhihuishu_store.save_status(username, {
            "worker": "error",
            "last_error": message,
        })
        logger.error("%s for %s", message, username)
        return False
    if result.returncode != 0:
        logger.error("Worker child exited with status %s for %s", result.returncode, username)
        return False
    return True


def _run_all_users_round(failures: dict[str, int], dry_run: bool = False, runner=None) -> dict[str, int]:
    runner = runner or _run_user_subprocess
    usernames = _all_usernames()
    current = set(usernames)
    failures = {username: failures.get(username, 0) for username in usernames}
    for username in usernames:
        try:
            ok = runner(username, dry_run=dry_run)
            failures[username] = 0 if ok else failures[username] + 1
        except Exception as exc:
            failures[username] = failures.get(username, 0) + 1
            zhihuishu_store.save_status(username, {
                "worker": "error",
                "last_error": str(exc),
            })
            logger.exception("Worker cycle failed for %s", username)
    return {username: failures[username] for username in usernames if username in current}


def _run_loop(usernames: list[str] | None = None, all_users: bool = False, dry_run: bool = False):
    failures = {}
    while True:
        if all_users:
            failures = _run_all_users_round(failures, dry_run=dry_run)
        else:
            current_usernames = usernames or []
            failures = {username: failures.get(username, 0) for username in current_usernames}
            for username in current_usernames:
                ok = _run_user_subprocess(username, dry_run=dry_run)
                failures[username] = 0 if ok else failures[username] + 1
        delay = min(next_delay_seconds(count) for count in failures.values()) if failures else KEEPALIVE_INTERVAL_SECONDS
        time.sleep(delay)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username")
    parser.add_argument("--all-users", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--child-cycle", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.child_cycle:
        if not args.once or not args.username or args.all_users:
            parser.error("--child-cycle requires --once and --username")
        try:
            return 0 if _run_once(args.username, dry_run=args.dry_run) else 1
        except Exception as exc:
            zhihuishu_store.save_status(args.username, {
                "worker": "error",
                "last_error": str(exc),
            })
            logger.exception("Worker child cycle failed for %s", args.username)
            return 1

    if args.all_users:
        usernames = _all_usernames()
    elif args.username:
        usernames = [args.username]
    else:
        parser.error("provide --username or --all-users")

    if args.once and args.dry_run:
        for username in usernames:
            _run_once(username, dry_run=True)
        return 0

    try:
        with single_instance_lock():
            if args.once:
                ok = True
                for username in usernames:
                    ok = _run_user_subprocess(username, dry_run=args.dry_run) and ok
                return 0 if ok else 1
            _run_loop(usernames, all_users=args.all_users, dry_run=args.dry_run)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
