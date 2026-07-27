"""Per-user data directory resolution, shared by all platform client modules."""
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def user_dir(username: str) -> Path:
    """Return (and create) the per-user data directory."""
    # Import lazily to avoid auth's legacy-data migration import cycle.  A
    # request already in flight must not recreate files after account deletion
    # has started in this process.
    try:
        import auth
        if auth.account_deletion_in_progress(username):
            raise RuntimeError("account deletion in progress")
    except ImportError:
        pass
    d = DATA_DIR / "users" / username
    d.mkdir(parents=True, exist_ok=True)
    return d
