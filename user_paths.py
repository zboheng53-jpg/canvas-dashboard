"""Per-user data directory resolution, shared by all platform client modules."""
import os
from pathlib import Path

# Set before importing the application. Tests and previews use disposable roots.
DATA_DIR = Path(os.environ.get("CANVAS_DASHBOARD_DATA_DIR") or Path(__file__).parent / "data").resolve()


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
