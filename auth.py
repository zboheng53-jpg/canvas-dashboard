"""Account identity, authentication and lifecycle primitives.

Usernames are deliberately reusable.  ``account_id`` is therefore the durable
identity used by sessions and deletion records; it must never be inferred from
a directory name alone.
"""
import hashlib
import logging
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from storage import locked_json_update, load_or_create_bytes, read_json_file, write_json_file, interprocess_lock

from user_paths import DATA_DIR
from maintenance import maintenance_lock
USERS_FILE = DATA_DIR / "users.json"
SECRET_KEY_FILE = DATA_DIR / ".flask_secret_key"
# Deliberately excluded from encrypted account-content backups.  It is merged
# into a restore before activation, so an old archive cannot revive an account.
DELETION_LEDGER_FILE = DATA_DIR / ".account_deletion_ledger.json"
ADMIN_AUDIT_FILE = DATA_DIR / "account_admin_audit.json"
QUARANTINE_DIR = DATA_DIR / ".quarantine"

logger = logging.getLogger(__name__)


def _isolate_user_dir(
    username: str,
    account_id: str | None = None,
    data_dir: Path | None = None,
    prefix: str = "del",
) -> tuple[bool, str | None, Path | None]:
    """Atomically move user directory into quarantine.

    Does NOT perform slow rmtree under caller's critical locks.
    Returns (ok, error_message, quarantined_path).
    """
    base_dir = Path(data_dir or DATA_DIR)
    user_path = base_dir / "users" / username
    if not user_path.exists():
        return True, None, None
    quarantine_dir = base_dir / ".quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    tag = account_id if account_id else username
    staged_path = quarantine_dir / f"{prefix}_{tag}_{int(time.time())}_{secrets.token_hex(4)}"
    try:
        user_path.rename(staged_path)
    except Exception as e:
        logger.error(f"Failed to isolate user directory for {username} to {staged_path}: {e}")
        return False, "用户数据目录隔离失败，请稍后重试", None
    return True, None, staged_path


def _clean_quarantine_path(path: Path | None) -> bool:
    """Best-effort cleanup of an isolated path."""
    if not path or not path.exists():
        return True
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        return True
    except Exception as e:
        logger.warning(f"Could not purge quarantine directory {path}: {e}")
        return False


def _isolate_and_remove_user_dir(
    username: str, data_dir: Path | None = None, account_id: str | None = None
) -> tuple[bool, str | None]:
    ok, err, staged = _isolate_user_dir(username, account_id=account_id, data_dir=data_dir)
    if not ok:
        return False, err
    if staged:
        _clean_quarantine_path(staged)
    return True, None


def purge_quarantine(data_dir: Path | None = None) -> dict[str, list[str]]:
    base_dir = Path(data_dir or DATA_DIR)
    with maintenance_lock(base_dir):
        return _purge_quarantine(base_dir)


def _purge_quarantine(data_dir: Path | None = None) -> dict[str, list[str]]:
    """Attempt to clean up any quarantined directories that were previously locked."""
    base_dir = Path(data_dir or DATA_DIR)
    quarantine_dir = base_dir / ".quarantine"
    result = {"purged": [], "failed": []}
    if not quarantine_dir.exists():
        return result
    for item in list(quarantine_dir.iterdir()):
        if not re.fullmatch(r"(?:del|orphan)_[A-Za-z0-9_-]+_\d+_[0-9a-f]{8}", item.name):
            continue
        if item.is_symlink() or not item.resolve().is_relative_to(quarantine_dir.resolve()):
            result["failed"].append(item.name)
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
            result["purged"].append(item.name)
        except Exception as e:
            logger.warning(f"Failed to purge quarantined item {item.name}: {e}")
            result["failed"].append(item.name)
    return result


def has_pending_quarantine(account_id: str | None = None, data_dir: Path | None = None) -> bool:
    """Check if any quarantined directory remains pending cleanup."""
    base_dir = Path(data_dir or DATA_DIR)
    quarantine_dir = base_dir / ".quarantine"
    if not quarantine_dir.exists():
        return False
    for item in quarantine_dir.iterdir():
        if account_id:
            if item.name.startswith(f"del_{account_id}_"):
                return True
        else:
            if item.name.startswith("del_") or item.name.startswith("orphan_"):
                return True
    return False


CST = timezone(timedelta(hours=8))
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
SESSION_LIFETIME = timedelta(days=30)
DELETE_CONFIRMATION = "永久删除"

_account_locks_guard = threading.Lock()
_account_locks: dict[str, threading.RLock] = {}
_deleting_accounts: set[str] = set()

_LEGACY_FILES = [
    "custom_todos.json", "config.json", "canvas_state.json", "haoke_state.json",
    "zhixuemeng_state.json", "zhihuishu_state.json", "zhihuishu_cache.json",
    "zhihuishu_cookies.json", "canvas_cache.json", "haoke_cache.json",
    "zhixuemeng_cache.json", "ketangpai_state.json", "ketangpai_cache.json",
]


def _now() -> str:
    return datetime.now(CST).isoformat()


def get_secret_key() -> str:
    return load_or_create_bytes(SECRET_KEY_FILE, lambda: secrets.token_hex(32).encode("utf-8")).decode("utf-8").strip()


def _account_lock(username: str) -> threading.RLock:
    with _account_locks_guard:
        return _account_locks.setdefault(username, threading.RLock())


@contextmanager
def account_operation(username: str, data_dir: Path | None = None):
    """Serialize local lifecycle actions for one account across threads and processes."""
    base_dir = Path(data_dir or DATA_DIR)
    locks_dir = base_dir / ".account_locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_file = locks_dir / hashlib.sha256(username.encode("utf-8")).hexdigest()
    with _account_lock(username):
        with interprocess_lock(lock_file):
            yield


def account_deletion_in_progress(username: str, data_dir: Path | None = None) -> bool:
    with _account_locks_guard:
        if username in _deleting_accounts:
            return True
    record = _record(username, data_dir=data_dir)
    return bool(record and record.get("status") == "deleting")


def _normalize_record(record: dict) -> tuple[dict, bool]:
    value = dict(record or {})
    changed = False
    defaults = {
        "account_id": secrets.token_urlsafe(24),
        "status": "active",
        "session_version": 1,
        "created_at": _now(),
        "last_login_at": None,
    }
    for key, default in defaults.items():
        if key not in value:
            value[key] = default
            changed = True
    if value.get("status") not in {"active", "suspended", "deleting"}:
        value["status"] = "active"
        changed = True
    if not isinstance(value.get("session_version"), int) or value["session_version"] < 1:
        value["session_version"] = 1
        changed = True
    return value, changed


def migrate_account_schema(data_dir: Path | None = None) -> dict:
    """Add identity/session metadata to legacy accounts without removing fields."""
    base_dir = Path(data_dir or DATA_DIR)
    users_file = base_dir / "users.json"
    changed = {"value": False}

    def migrate(users):
        if not isinstance(users, dict):
            return users
        for username, record in list(users.items()):
            if not isinstance(record, dict):
                continue
            normalized, record_changed = _normalize_record(record)
            if record_changed:
                users[username] = normalized
                changed["value"] = True
        return users

    return locked_json_update(users_file, {}, migrate)


def _load_users(data_dir: Path | None = None) -> dict:
    base_dir = Path(data_dir or DATA_DIR)
    users = read_json_file(base_dir / "users.json", {})
    if not isinstance(users, dict):
        return {}
    # A small, idempotent migration keeps old production data compatible.
    if any(isinstance(value, dict) and "account_id" not in value for value in users.values()):
        users = migrate_account_schema(data_dir=base_dir)
    return users


def _record(username: str, data_dir: Path | None = None) -> dict | None:
    record = _load_users(data_dir=data_dir).get((username or "").strip())
    return record if isinstance(record, dict) else None


def user_exists(username: str) -> bool:
    return _record(username) is not None


def active_usernames() -> list[str]:
    return sorted(username for username, record in _load_users().items() if isinstance(record, dict) and record.get("status") == "active")


def account_metadata(username: str) -> dict | None:
    record = _record(username)
    if not record:
        return None
    return {key: record.get(key) for key in ("account_id", "status", "created_at", "last_login_at", "session_version")}


def session_identity(username: str) -> tuple[str, int] | None:
    record = _record(username)
    if not record or record.get("status") != "active":
        return None
    return record["account_id"], record["session_version"]


def validate_session_identity(username: str, account_id: str | None, session_version: int | None) -> bool:
    expected = session_identity(username)
    return bool(expected and account_id == expected[0] and session_version == expected[1])


def _migrate_legacy_data(username: str):
    from user_paths import user_dir
    destination = user_dir(username)
    for filename in _LEGACY_FILES:
        source = DATA_DIR / filename
        if source.exists():
            source.rename(destination / filename)


def register(username: str, password: str):
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        return False, "用户名需为 3-20 位字母、数字或下划线"
    if not password or len(password) < 6:
        return False, "密码至少需要 6 位"
    record = {
        "password_hash": generate_password_hash(password), "created_at": _now(),
        "last_login_at": _now(), "account_id": secrets.token_urlsafe(24),
        "status": "active", "session_version": 1,
    }
    result = {"ok": False, "error": "用户名已被注册", "staged": None}
    with account_operation(username):
        def add_user(users):
            if username in users:
                return users
            ok, error, staged = _isolate_user_dir(username, prefix="orphan")
            if not ok:
                result["error"] = error
                return users
            result["staged"] = staged
            if not users:
                _migrate_legacy_data(username)
            result["ok"] = True
            users[username] = record
            return users
        with maintenance_lock(DATA_DIR):
            locked_json_update(USERS_FILE, {}, add_user)
    _clean_quarantine_path(result["staged"])
    return (True, None) if result["ok"] else (False, result["error"])


def verify_login(username: str, password: str) -> dict | None:
    username = (username or "").strip()
    record = _record(username)
    if not record or record.get("status") != "active" or not check_password_hash(record.get("password_hash", ""), password):
        return None
    account_id = record.get("account_id")
    session_version = record.get("session_version")

    login_recorded = {"ok": False}
    def note_login(users):
        u = users.get(username)
        if (
            isinstance(u, dict)
            and u.get("status") == "active"
            and u.get("account_id") == account_id
            and u.get("session_version") == session_version
        ):
            u["last_login_at"] = _now()
            login_recorded["ok"] = True
        return users

    locked_json_update(USERS_FILE, {}, note_login)
    if not login_recorded["ok"]:
        return None

    return {
        "username": username,
        "account_id": account_id,
        "session_version": session_version,
    }


def revoke_other_sessions(username: str, password: str) -> tuple[bool, int | None]:
    """Invalidate every old cookie while allowing the caller to retain its session."""
    username = (username or "").strip()
    changed = {"ok": False, "version": None}
    with account_operation(username):
        def revoke(users):
            record = users.get(username)
            if not isinstance(record, dict) or not check_password_hash(record.get("password_hash", ""), password):
                return users
            record, _ = _normalize_record(record)
            record["session_version"] += 1
            users[username] = record
            changed.update(ok=True, version=record["session_version"])
            return users
        locked_json_update(USERS_FILE, {}, revoke)
    return changed["ok"], changed["version"]


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str | None]:
    username = (username or "").strip()
    if not new_password or len(new_password) < 6:
        return False, "密码至少需要 6 位"
    changed = {"ok": False, "account_id": None}
    with account_operation(username):
        def update(users):
            record = users.get(username)
            if not isinstance(record, dict) or not check_password_hash(record.get("password_hash", ""), old_password):
                return users
            record, _ = _normalize_record(record)
            record["password_hash"] = generate_password_hash(new_password)
            record["session_version"] = int(record.get("session_version", 1)) + 1
            users[username] = record
            changed.update(ok=True, account_id=record["account_id"])
            return users
        locked_json_update(USERS_FILE, {}, update)
    if changed["ok"]:
        _append_audit(username, "change_password", "user_requested", "ok", changed["account_id"])
        return True, None
    return False, "原密码不正确"


def _ledger() -> dict:
    return read_json_file(DELETION_LEDGER_FILE, {"version": 1, "deleted_accounts": {}})


def _record_deletion(account_id: str, reason: str) -> None:
    def add_entry(ledger):
        ledger.setdefault("version", 1)
        ledger.setdefault("deleted_accounts", {})[account_id] = {"deleted_at": _now(), "reason": reason}
        return ledger
    locked_json_update(DELETION_LEDGER_FILE, {"version": 1, "deleted_accounts": {}}, add_entry)


def apply_deletion_ledger(data_dir: Path | None = None, ledger_path: Path | None = None) -> list[str]:
    """Remove only restored account instances whose immutable IDs were deleted."""
    data_dir = Path(data_dir or DATA_DIR)
    ledger_path = Path(ledger_path or DELETION_LEDGER_FILE)
    deleted_ids = set(read_json_file(ledger_path, {"deleted_accounts": {}}).get("deleted_accounts", {}))
    if not deleted_ids:
        return []
    users_file = data_dir / "users.json"
    removed = []

    for username, candidate in _load_users(data_dir).items():
        if not isinstance(candidate, dict) or candidate.get("account_id") not in deleted_ids:
            continue
        with account_operation(username, data_dir), maintenance_lock(data_dir):
            staged = {"path": None}
            def remove_deleted(users):
                record = users.get(username)
                if not isinstance(record, dict) or record.get("account_id") != candidate["account_id"]:
                    return users
                ok, error, path = _isolate_user_dir(username, candidate["account_id"], data_dir)
                if not ok:
                    raise OSError(error)
                staged["path"] = path
                users.pop(username)
                removed.append(username)
                return users
            locked_json_update(users_file, {}, remove_deleted)
        _clean_quarantine_path(staged["path"])
    return removed


def _finish_deletion(username: str, record: dict, reason: str, cleanup=None) -> tuple[bool, str | None]:
    """Caller holds the stable account lock; slow resource cleanup never holds users.json."""
    account_id = record["account_id"]
    with maintenance_lock(DATA_DIR):
        def mark_deleting(users):
            current = users.get(username)
            if not current or current.get("account_id") != account_id:
                raise RuntimeError("account identity changed")
            if current.get("status") != "deleting":
                current["status"] = "deleting"
                current["session_version"] += 1
            return users
        locked_json_update(USERS_FILE, {}, mark_deleting)
        # A failed ledger write leaves an inactive, retryable record and intact data.
        _record_deletion(account_id, reason)
    if cleanup is None:
        def cleanup():
            import tongji_login_sessions
            import zhihuishu_login_sessions
            zhihuishu_login_sessions.stop_session(username)
            tongji_login_sessions.stop_session(username)
    from login_capacity import account_profile_lock
    try:
        with account_profile_lock(DATA_DIR, username, timeout=5):
            cleanup()
            with maintenance_lock(DATA_DIR):
                ok, error, staged = _isolate_user_dir(username, account_id)
                if not ok:
                    return False, error
                def remove_user(users):
                    current = users.get(username)
                    if current and current.get("account_id") == account_id and current.get("status") == "deleting":
                        users.pop(username)
                    return users
                locked_json_update(USERS_FILE, {}, remove_user)
    except Exception:
        logger.warning("Account resource cleanup pending")
        return False, "账户已停用，认证资源清理失败，后台将重试删除"
    purged = _clean_quarantine_path(staged)
    _append_audit(username, "delete", reason, "ok" if purged else "cleanup_pending", account_id)
    return True, None if purged else "账户已删除，隔离区中的旧数据等待后台重试清理"


def delete_account(
    username: str,
    password: str,
    confirmation: str,
    reason: str = "user_requested",
    expected_account_id: str | None = None,
    expected_session_version: int | None = None,
    before_delete: Callable[[], None] | None = None,
) -> tuple[bool, str | None]:
    username = (username or "").strip()
    if not password:
        return False, "请输入当前密码"
    if confirmation != DELETE_CONFIRMATION:
        return False, f"请准确输入“{DELETE_CONFIRMATION}”"
    with account_operation(username):
        record = _record(username)
        if not record or not check_password_hash(record.get("password_hash", ""), password):
            return False, "当前密码不正确"
        if expected_account_id and record.get("account_id") != expected_account_id:
            return False, "账户信息已变更，请重新验证"
        if expected_session_version is not None and record.get("session_version") != expected_session_version:
            return False, "账户信息已变更，请重新验证"

        try:
            return _finish_deletion(username, record, reason, before_delete)
        except OSError:
            logger.warning("Account deletion ledger write failed; data retained")
            return False, "账户已停用，删除记录写入失败，数据保留并等待后台重试"


def _delete_account_without_password(username: str, reason: str) -> bool:
    """Lifecycle-only deletion used for a conservatively verified blank account."""
    with account_operation(username):
        record = _record(username)
        if not record:
            return False
        directory = DATA_DIR / "users" / username
        if directory.exists() and any(directory.iterdir()):
            return False
        return _finish_deletion(username, record, reason)[0]


def retry_pending_deletions() -> list[str]:
    removed = []
    for username, candidate in _load_users().items():
        if not isinstance(candidate, dict) or candidate.get("status") != "deleting":
            continue
        with account_operation(username):
            current = _record(username)
            if not current or current.get("account_id") != candidate["account_id"] or current.get("status") != "deleting":
                continue
            try:
                if _finish_deletion(username, current, "retry_pending_deletion")[0]:
                    removed.append(username)
            except OSError:
                logger.warning("Account deletion remains pending")
    return removed


def purge_blank_inactive_accounts(now: datetime | None = None, idle_days: int = 90) -> list[str]:
    """Delete only accounts with no user directory entries whatsoever.

    This intentionally treats every file, unknown file, or read failure as
    user content.  It may keep an eligible account longer, but never deletes
    an account because a cache/configuration could not be interpreted.
    """
    now = now or datetime.now(CST)
    removed = []
    for username, record in _load_users().items():
        if not isinstance(record, dict) or record.get("status") != "active":
            continue
        try:
            last_login = datetime.fromisoformat(record.get("last_login_at") or record.get("created_at"))
            if last_login.tzinfo is None:
                last_login = last_login.replace(tzinfo=CST)
        except (TypeError, ValueError):
            continue
        if now - last_login < timedelta(days=idle_days):
            continue
        directory = DATA_DIR / "users" / username
        try:
            is_blank = not directory.exists() or not any(directory.iterdir())
        except OSError:
            is_blank = False
        if is_blank and _delete_account_without_password(username, "auto_blank_90_days"):
            removed.append(username)
    return removed


def _append_audit(username: str, action: str, reason: str, outcome: str, account_id: str | None = None) -> None:
    def append(entries):
        entries.append({"at": _now(), "account_id": account_id, "username_hash": hashlib.sha256(username.encode()).hexdigest(), "action": action, "reason": reason[:240], "outcome": outcome})
        return entries[-1000:]
    locked_json_update(ADMIN_AUDIT_FILE, [], append)


def set_account_status(username: str, status: str, reason: str) -> bool:
    if status not in {"active", "suspended"}:
        raise ValueError("unsupported account status")
    changed = {"value": False, "account_id": None}
    with account_operation(username):
        def update(users):
            record = users.get(username)
            if not isinstance(record, dict) or record.get("status") == "deleting":
                return users
            record, _ = _normalize_record(record)
            record["status"] = status
            record["session_version"] += 1
            users[username] = record
            changed.update(value=True, account_id=record["account_id"])
            return users
        locked_json_update(USERS_FILE, {}, update)
    if changed["value"]:
        _append_audit(username, status, reason, "ok", changed["account_id"])
    return changed["value"]


def issue_password_reset(username: str, ttl_minutes: int = 30) -> str | None:
    token = secrets.token_urlsafe(32)
    changed = {"value": False, "account_id": None}
    def issue(users):
        record = users.get(username)
        if not isinstance(record, dict):
            return users
        record, _ = _normalize_record(record)
        record["reset_token_hash"] = hashlib.sha256(token.encode()).hexdigest()
        record["reset_expires_at"] = (datetime.now(CST) + timedelta(minutes=ttl_minutes)).isoformat()
        users[username] = record
        changed.update(value=True, account_id=record["account_id"])
        return users
    locked_json_update(USERS_FILE, {}, issue)
    if changed["value"]:
        _append_audit(username, "issue_password_reset", "offline_assistance", "ok", changed["account_id"])
        return token
    return None


def reset_password(username: str, token: str, new_password: str) -> tuple[bool, str | None]:
    if not new_password or len(new_password) < 6:
        return False, "密码至少需要 6 位"
    result = {"ok": False, "account_id": None}
    supplied_hash = hashlib.sha256((token or "").encode()).hexdigest()
    def reset(users):
        record = users.get(username)
        if not isinstance(record, dict):
            return users
        try:
            expires_at = datetime.fromisoformat(record.get("reset_expires_at", ""))
        except (TypeError, ValueError):
            return users
        if expires_at < datetime.now(CST) or not secrets.compare_digest(record.get("reset_token_hash", ""), supplied_hash):
            return users
        record["password_hash"] = generate_password_hash(new_password)
        record["session_version"] = int(record.get("session_version", 1)) + 1
        record.pop("reset_token_hash", None)
        record.pop("reset_expires_at", None)
        users[username] = record
        result.update(ok=True, account_id=record.get("account_id"))
        return users
    locked_json_update(USERS_FILE, {}, reset)
    if result["ok"]:
        _append_audit(username, "password_reset", "offline_assistance", "ok", result["account_id"])
        return True, None
    return False, "重置凭证无效或已过期"
