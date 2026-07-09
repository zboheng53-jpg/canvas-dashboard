"""Site-wide account system: open self-registration, password login, legacy data migration."""
import re
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

from storage import read_json_file, write_json_file

DATA_DIR = Path(__file__).parent / "data"
USERS_FILE = DATA_DIR / "users.json"
SECRET_KEY_FILE = DATA_DIR / ".flask_secret_key"

CST = timezone(timedelta(hours=8))
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")

# Permanent login, per user request ("一次登录之后就永久有效").
SESSION_LIFETIME = timedelta(days=3650)

# Top-level single-user data files from before multi-tenant support existed.
# Adopted by whichever account registers first, then removed from the top level.
_LEGACY_FILES = [
    "custom_todos.json", "config.json",
    "canvas_state.json", "haoke_state.json", "zhixuemeng_state.json",
    "zhihuishu_state.json", "zhihuishu_cache.json", "zhihuishu_cookies.json",
    "canvas_cache.json", "haoke_cache.json", "zhixuemeng_cache.json",
]


def get_secret_key() -> str:
    """Load or generate a persisted Flask session secret key."""
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    return key


def _load_users() -> dict:
    return read_json_file(USERS_FILE, {})


def _save_users(users: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json_file(USERS_FILE, users)


def user_exists(username: str) -> bool:
    return username in _load_users()


def _migrate_legacy_data(username: str):
    """Move old top-level single-user data files into the first account's directory."""
    from user_paths import user_dir
    dest = user_dir(username)
    for fname in _LEGACY_FILES:
        src = DATA_DIR / fname
        if src.exists():
            src.rename(dest / fname)


def register(username: str, password: str):
    """Create a new account. Returns (ok: bool, error: str | None)."""
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        return False, "用户名需为 3-20 位字母、数字或下划线"
    if not password or len(password) < 6:
        return False, "密码至少需要 6 位"

    users = _load_users()
    if username in users:
        return False, "用户名已被注册"

    is_first_account = len(users) == 0
    users[username] = {
        "password_hash": generate_password_hash(password),
        "created_at": datetime.now(CST).isoformat(),
    }
    _save_users(users)

    if is_first_account:
        _migrate_legacy_data(username)

    return True, None


def verify_login(username: str, password: str) -> bool:
    users = _load_users()
    record = users.get((username or "").strip())
    if not record:
        return False
    return check_password_hash(record["password_hash"], password)
