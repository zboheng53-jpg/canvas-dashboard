"""Background worker for keeping Zhihuishu data cached outside Flask requests."""
import argparse
import logging
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import settings
import auth
import zhihuishu_store
import platform_sync
from storage import read_json_file, write_json_file

KEEPALIVE_INTERVAL_SECONDS = settings.ZHIHUISHU_KEEPALIVE_INTERVAL_SECONDS
FETCH_INTERVAL_SECONDS = settings.ZHIHUISHU_FETCH_INTERVAL_SECONDS
MAX_FAILURE_DELAY_SECONDS = settings.ZHIHUISHU_MAX_FAILURE_DELAY_SECONDS
FETCH_TIMEOUT_SECONDS = settings.ZHIHUISHU_FETCH_TIMEOUT_SECONDS

LOCK_FILE = zhihuishu_store.DATA_DIR / "zhihuishu_worker.lock"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [zhihuishu-worker] %(levelname)s: %(message)s")
logger = logging.getLogger("zhihuishu_worker")


def next_delay_seconds(failure_count: int) -> int:
    return min(KEEPALIVE_INTERVAL_SECONDS * (2 ** max(0, failure_count)), MAX_FAILURE_DELAY_SECONDS)


def save_heartbeat():
    write_json_file(zhihuishu_store.DATA_DIR / 'worker_heartbeat.json', {'pid': os.getpid(), 'at': time.time()})


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
    # Account records are authoritative; an orphaned directory must never
    # cause a deleted/suspended account to be synchronised or recreated.
    if auth.DATA_DIR.resolve() == zhihuishu_store.DATA_DIR.resolve():
        usernames = []
        for username in auth.active_usernames():
            status_path = zhihuishu_store.DATA_DIR / "users" / username / "zhihuishu_status.json"
            if not status_path.exists():
                continue
            status = read_json_file(status_path, {})
            # Only accounts with active connected session enter browser checks
            if status.get("session") == "active":
                usernames.append(username)
        return usernames
    # Isolated test/maintenance roots deliberately monkeypatch only the
    # worker store. They have no account registry to consult.
    users_dir = zhihuishu_store.DATA_DIR / "users"
    if not users_dir.exists():
        return []
    result = []
    for path in sorted(users_dir.iterdir()):
        if not path.is_dir():
            continue
        status_path = path / "zhihuishu_status.json"
        if status_path.exists():
            status = read_json_file(status_path, {})
            if status.get("session") in ("disconnected", "need_relogin"):
                continue
        result.append(path.name)
    return result


def _is_active_username(username: str) -> bool:
    if auth.DATA_DIR.resolve() == zhihuishu_store.DATA_DIR.resolve():
        return auth.session_identity(username) is not None
    return (zhihuishu_store.DATA_DIR / 'users' / username).is_dir()


def _capture_owner(username):
    with auth.account_operation(username, zhihuishu_store.DATA_DIR):
        if not _is_active_username(username):
            return None
        authoritative = auth.DATA_DIR.resolve() == zhihuishu_store.DATA_DIR.resolve()
        identity = auth.session_identity(username) if authoritative else None
        return (identity, zhihuishu_store.load_status(username).get('connection_revision', 0))


def _owner_is_current(username, owner):
    if owner is None or not _is_active_username(username):
        return False
    identity, revision = owner
    if auth.DATA_DIR.resolve() == zhihuishu_store.DATA_DIR.resolve():
        if auth.session_identity(username) != identity:
            return False
    return zhihuishu_store.load_status(username).get('connection_revision', 0) == revision


def _publish_status(username, owner, updates, error_code=None):
    with auth.account_operation(username, zhihuishu_store.DATA_DIR):
        if not _owner_is_current(username, owner):
            return False
        zhihuishu_store.save_status(username, updates)
        if error_code:
            platform_sync.record_result(
                username, 'zhihuishu', ok=False,
                has_cache=bool(zhihuishu_store.load_cache(username)['items']),
                error_code=error_code, error_message=updates['last_error'],
            )
        return True


def _browser_module():
    browser = globals().get("zhihuishu_browser")
    if browser is not None:
        return browser
    import zhihuishu_browser as browser
    return browser


def run_scheduled_cycle(username: str, now: float | None = None, force_fetch: bool = False, expected_owner=None) -> bool:
    from login_capacity import worker_browser_slot, account_profile_lock, LoginCapacityError
    try:
        with account_profile_lock(zhihuishu_store.DATA_DIR, username, timeout=5.0, for_worker=True):
            with worker_browser_slot(zhihuishu_store.DATA_DIR, username):
                return _run_scheduled_cycle(username, now, force_fetch, expected_owner)
    except (LoginCapacityError, TimeoutError):
        logger.info('Browser resources busy; deferring cycle')
        return False


def _run_scheduled_cycle(username, now=None, force_fetch=False, expected_owner=None):
    if not _is_active_username(username):
        return False
    authoritative = auth.DATA_DIR.resolve() == zhihuishu_store.DATA_DIR.resolve()
    identity = auth.session_identity(username) if authoritative else None
    now = now or time.time()
    status = zhihuishu_store.load_status(username)
    revision = status.get('connection_revision', 0)
    if expected_owner is not None and (identity, revision) != expected_owner:
        return False
    if status.get('session') != 'active' and not force_fetch:
        return False
    last_fetch_at = status.get('last_fetch_at')
    should_fetch = force_fetch or not last_fetch_at or (now - float(last_fetch_at)) >= FETCH_INTERVAL_SECONDS
    browser = _browser_module()
    if hasattr(browser, 'run_user_cycle'):
        result = browser.run_user_cycle(username, should_fetch=should_fetch, force_fetch=force_fetch, now=now)
        session_ok = bool(result.get('session_ok'))
        fetch_res = result.get('fetch_result')
    else:
        session_ok = browser.check_session(username)
        fetch_res = None
        if session_ok:
            browser.keepalive(username)
            if should_fetch:
                fetch_res = browser.fetch_assignments(username)
    with auth.account_operation(username, zhihuishu_store.DATA_DIR):
        if authoritative and auth.session_identity(username) != identity:
            return False
        if zhihuishu_store.load_status(username).get('connection_revision', 0) != revision:
            return False
        if not session_ok:
            zhihuishu_store.save_status(username, {'session': 'need_relogin', 'worker': 'running', 'last_error': '智慧树登录态失效'})
            platform_sync.record_result(username, 'zhihuishu', ok=False,
                has_cache=bool(zhihuishu_store.load_cache(username)['items']),
                error_code='needs_reauth', error_message='智慧树登录态失效', needs_reauth=True)
            return False
        updates = {'session': 'active', 'worker': 'running', 'last_keepalive_at': now, 'last_error': ''}
        if should_fetch and fetch_res is not None:
            if not _is_active_username(username):
                return False

            if hasattr(fetch_res, "ok"):
                ok = fetch_res.ok
                partial = fetch_res.partial
                items = fetch_res.items
                failed_courses = fetch_res.failed_courses
            elif isinstance(fetch_res, dict):
                ok = fetch_res.get("ok", True)
                partial = fetch_res.get("partial", False)
                items = fetch_res.get("items", [])
                failed_courses = fetch_res.get("failed_courses", [])
            else:
                ok = True
                partial = False
                items = fetch_res or []
                failed_courses = []

            old_cache = zhihuishu_store.load_cache(username)

            if not ok:
                err_msg = f"抓取失败: 全部课程抓取失败 ({', '.join(failed_courses)})" if failed_courses else "抓取失败: 智慧树无有效响应"
                updates["worker"] = "error"
                updates["last_error"] = err_msg
                zhihuishu_store.save_status(username, updates)
                platform_sync.record_result(
                    username, "zhihuishu", ok=False,
                    has_cache=bool(old_cache["items"]),
                    error_code="fetch_failed", error_message=err_msg,
                )
                return False

            if partial and failed_courses:
                succeeded = set(getattr(fetch_res, 'succeeded_courses', [])) or {it.get('course') for it in items}
                succeeded -= set(failed_courses)
                preserved_old = [
                    it for it in old_cache.get("items", [])
                    if it.get("course") not in succeeded
                ]
                seen_ids = {it["id"] for it in items}
                merged = list(items)
                for it in preserved_old:
                    if it["id"] not in seen_ids:
                        merged.append(it)
                        seen_ids.add(it["id"])
                items_to_save = merged
                updates["partial_fetch"] = True
                updates["failed_courses"] = failed_courses
                updates["last_error"] = f"部分课程抓取失败: {', '.join(failed_courses)}"
            else:
                items_to_save = items
                updates["partial_fetch"] = False
                updates["failed_courses"] = []
                updates["last_error"] = ""

            zhihuishu_store.save_cache(username, items_to_save, fetched_at=now)
            updates['last_attempt_at'] = now
            if not partial:
                updates["last_fetch_at"] = now
                updates["last_success_at"] = now
            platform_sync.record_result(
                username, "zhihuishu", ok=not partial,
                has_cache=bool(items_to_save),
                error_code='partial_fetch' if partial else None,
                error_message=updates.get("last_error", ""),
            )

        zhihuishu_store.save_status(username, updates)
        return not bool(updates.get('partial_fetch'))


def _run_once(username: str, dry_run: bool = False, force_fetch: bool = False, expected_owner=None) -> bool:
    now = time.time()
    if dry_run:
        zhihuishu_store.save_status(username, {
            "worker": "dry_run",
            "last_keepalive_at": now,
            "last_error": "",
        })
        return True

    return run_scheduled_cycle(username, now=now, force_fetch=force_fetch, expected_owner=expected_owner)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False, capture_output=True, timeout=10)
        else:
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
    except Exception:
        pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass


def _run_user_subprocess(username: str, dry_run: bool = False, force_fetch: bool = False) -> bool:
    owner = _capture_owner(username)
    if owner is None:
        return False
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
    if force_fetch:
        command.append("--force-fetch")
    if owner[0] is not None:
        command.extend(['--account-id', owner[0][0], '--connection-revision', str(owner[1])])

    popen_kwargs = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(command, **popen_kwargs)
        try:
            returncode = proc.wait(timeout=FETCH_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            message = f"worker cycle timed out after {FETCH_TIMEOUT_SECONDS} seconds"
            _publish_status(username, owner, {
                "worker": "error",
                "last_error": message,
            }, error_code='worker_timeout')
            logger.error("%s for %s", message, username)
            return False
    except Exception as exc:
        logger.exception("Worker child execution failed for %s", username)
        return False

    if returncode != 0:
        logger.error("Worker child exited with status %s for %s", returncode, username)
        return False
    return True


def _run_all_users_round(failures: dict[str, int], dry_run: bool = False, runner=None, now: float | None = None) -> dict[str, int]:
    runner = runner or _run_user_subprocess
    usernames = _all_usernames()
    current = set(usernames)
    now = time.time() if now is None else now

    # Per-account next_attempt_at backoff: skip users whose backoff hasn't expired
    ready_users = []
    for username in usernames:
        status = zhihuishu_store.load_status(username)
        next_attempt = float(status.get("next_attempt_at") or 0)
        if next_attempt > now:
            logger.debug("Skipping %s due to backoff until %s", username, next_attempt)
            continue
        ready_users.append(username)

    # Fair scheduling: prioritize accounts with oldest activity
    def priority_key(u: str):
        st = zhihuishu_store.load_status(u)
        lf = float(st.get("last_fetch_at") or 0)
        lk = float(st.get("last_keepalive_at") or 0)
        return (min(lf, lk), u)

    sorted_users = sorted(ready_users, key=priority_key)
    failures = {username: failures.get(username, 0) for username in usernames}

    for username in sorted_users:
        save_heartbeat()
        owner = _capture_owner(username)
        if owner is None:
            continue
        try:
            ok = runner(username, dry_run=dry_run)
            if ok:
                failures[username] = 0
                _publish_status(username, owner, {
                    "failure_count": 0,
                    "next_attempt_at": 0,
                })
            else:
                count = failures[username] + 1
                failures[username] = count
                delay = next_delay_seconds(count - 1)
                _publish_status(username, owner, {
                    "failure_count": count,
                    "next_attempt_at": now + delay,
                })
        except Exception as exc:
            count = failures.get(username, 0) + 1
            failures[username] = count
            delay = next_delay_seconds(count - 1)
            message = f'后台同步异常 ({type(exc).__name__})'
            _publish_status(username, owner, {
                "worker": "error",
                "last_error": message,
                "failure_count": count,
                "next_attempt_at": now + delay,
            }, error_code='worker_failed')
            logger.error('Worker cycle failed: %s', type(exc).__name__)

    return {username: failures[username] for username in usernames if username in current}


def _run_loop(usernames: list[str] | None = None, all_users: bool = False, dry_run: bool = False):
    failures = {}
    while True:
        save_heartbeat()
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
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--child-cycle", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument('--account-id', help=argparse.SUPPRESS)
    parser.add_argument('--connection-revision', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.child_cycle:
        if not args.once or not args.username or args.all_users:
            parser.error("--child-cycle requires --once and --username")
        owner = _capture_owner(args.username)
        if owner is None:
            return 1
        if args.account_id and (owner[0] is None or owner[0][0] != args.account_id or owner[1] != args.connection_revision):
            return 1
        try:
            return 0 if _run_once(args.username, dry_run=args.dry_run, force_fetch=args.force_fetch, expected_owner=owner) else 1
        except Exception as exc:
            _publish_status(args.username, owner, {
                "worker": "error",
                "last_error": f'后台同步异常 ({type(exc).__name__})',
            }, error_code='worker_failed')
            logger.error('Worker child cycle failed: %s', type(exc).__name__)
            return 1

    if args.all_users:
        usernames = _all_usernames()
    elif args.username:
        usernames = [args.username]
    else:
        parser.error("provide --username or --all-users")

    if args.once and args.dry_run:
        for username in usernames:
            _run_once(username, dry_run=True, force_fetch=args.force_fetch)
        return 0

    try:
        with single_instance_lock():
            if args.once:
                ok = True
                for username in usernames:
                    ok = _run_user_subprocess(username, dry_run=args.dry_run, force_fetch=args.force_fetch) and ok
                return 0 if ok else 1
            _run_loop(usernames, all_users=args.all_users, dry_run=args.dry_run)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
