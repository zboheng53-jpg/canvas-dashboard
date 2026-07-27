"""Account identity, authentication and lifecycle primitives.

Usernames are deliberately reusable.  ``account_id`` is therefore the durable
identity used by sessions and deletion records; it must never be inferred from
a directory name alone.
"""
import hashlib
import re
import secrets
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from storage import locked_json_update, load_or_create_bytes, read_json_file, write_json_file

DATA_DIR = Path(__file__).parent / "data"
USERS_FILE = DATA_DIR / "users.json"
SECRET_KEY_FILE = DATA_DIR / ".flask_secret_key"
# Deliberately excluded from encrypted account-content backups.  It is merged
# into a restore before activation, so an old archive cannot revive an account.
DELETION_LEDGER_FILE = DATA_DIR / ".account_deletion_ledger.json"
ADMIN_AUDIT_FILE = DATA_DIR / "account_admin_audit.json"

CST = timezone(timedelta(hours=8))
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
SESSION_LIFETIME = timedelta(days=3650)
DELETE_CONFIRMATION = "永久删除"

_account_locks_guard = threading.Lock()
_account_locks: dict[str, threading.RLock] = {}
_deleting_accounts: set[str] = set()

_LEGACY_FILES = [
    "custom_todos.json", "config.json", "canvas_state.json", "haoke_state.json",
    "zhixuemeng_state.json", "zhihuishu_state.json", "zhihuishu_cache.json",
    "zhihuishu_cookies.json", "canvas_cache.json", "haoke_cache.json",
    "zhixuemeng_cache.json",
]


def _now() -> str:
    return datetime.now(CST).isoformat()


def get_secret_key() -> str:
    return load_or_create_bytes(SECRET_KEY_FILE, lambda: secrets.token_hex(32).encode("utf-8")).decode("utf-8").strip()


def _account_lock(username: str) -> threading.RLock:
    with _account_locks_guard:
        return _account_locks.setdefault(username, threading.RLock())


@contextmanager
def account_operation(username: str):
    """Serialize local lifecycle actions for one account."""
    with _account_lock(username):
        yield


def account_deletion_in_progress(username: str) -> bool:
    with _account_locks_guard:
        return username in _deleting_accounts


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
    if value.get("status") not in {"active", "suspended"}:
        value["status"] = "active"
        changed = True
    if not isinstance(value.get("session_version"), int) or value["session_version"] < 1:
        value["session_version"] = 1
        changed = True
    return value, changed


def migrate_account_schema() -> dict:
    """Add identity/session metadata to legacy accounts without removing fields."""
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

    return locked_json_update(USERS_FILE, {}, migrate)


def _load_users() -> dict:
    users = read_json_file(USERS_FILE, {})
    if not isinstance(users, dict):
        return {}
    # A small, idempotent migration keeps old production data compatible.
    if any(isinstance(value, dict) and "account_id" not in value for value in users.values()):
        users = migrate_account_schema()
    return users


def _record(username: str) -> dict | None:
    record = _load_users().get((username or "").strip())
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
    if not password or len(password) < 8:
        return False, "密码至少需要 8 位"
    record = {
        "password_hash": generate_password_hash(password), "created_at": _now(),
        "last_login_at": _now(), "account_id": secrets.token_urlsafe(24),
        "status": "active", "session_version": 1,
    }
    result = {"ok": False, "is_first_account": False}
    with account_operation(username):
        def add_user(users):
            if username in users:
                return users
            result["ok"] = True
            result["is_first_account"] = len(users) == 0
            users[username] = record
            return users
        locked_json_update(USERS_FILE, {}, add_user)
        if result["ok"] and result["is_first_account"]:
            _migrate_legacy_data(username)
    return (True, None) if result["ok"] else (False, "用户名已被注册")


def verify_login(username: str, password: str) -> bool:
    username = (username or "").strip()
    record = _record(username)
    if not record or record.get("status") != "active" or not check_password_hash(record.get("password_hash", ""), password):
        return False
    def note_login(users):
        if username in users:
            users[username]["last_login_at"] = _now()
        return users
    locked_json_update(USERS_FILE, {}, note_login)
    return True


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
    users_file = data_dir / "users.json"
    users = read_json_file(users_file, {})
    removed = []
    for username, record in list(users.items()):
        if isinstance(record, dict) and record.get("account_id") in deleted_ids:
            users.pop(username, None)
            shutil.rmtree(data_dir / "users" / username, ignore_errors=True)
            removed.append(username)
    if removed:
        write_json_file(users_file, users)
    return removed


def delete_account(username: str, password: str, confirmation: str, reason: str = "user_requested") -> tuple[bool, str | None]:
    username = (username or "").strip()
    if confirmation != DELETE_CONFIRMATION:
        return False, f"请准确输入“{DELETE_CONFIRMATION}”"
    with account_operation(username):
        record = _record(username)
        if not record or not check_password_hash(record.get("password_hash", ""), password):
            return False, "当前密码不正确"
        with _account_locks_guard:
            _deleting_accounts.add(username)
        try:
            _record_deletion(record["account_id"], reason)
            def remove_user(users):
                users.pop(username, None)
                return users
            locked_json_update(USERS_FILE, {}, remove_user)
            shutil.rmtree(DATA_DIR / "users" / username, ignore_errors=True)
            _append_audit(username, "delete", reason, "ok", record["account_id"])
        finally:
            with _account_locks_guard:
                _deleting_accounts.discard(username)
    return True, None


def _delete_account_without_password(username: str, reason: str) -> bool:
    """Lifecycle-only deletion used for a conservatively verified blank account."""
    with account_operation(username):
        record = _record(username)
        if not record:
            return False
        with _account_locks_guard:
            _deleting_accounts.add(username)
        try:
            _record_deletion(record["account_id"], reason)
            locked_json_update(USERS_FILE, {}, lambda users: {key: value for key, value in users.items() if key != username})
            shutil.rmtree(DATA_DIR / "users" / username, ignore_errors=True)
            _append_audit(username, "delete", reason, "ok", record["account_id"])
            return True
        finally:
            with _account_locks_guard:
                _deleting_accounts.discard(username)


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
            if not isinstance(record, dict):
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
    if not new_password or len(new_password) < 8:
        return False, "密码至少需要 8 位"
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
