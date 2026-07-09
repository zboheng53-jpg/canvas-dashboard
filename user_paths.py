"""Per-user data directory resolution, shared by all platform client modules."""
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def user_dir(username: str) -> Path:
    """Return (and create) the per-user data directory."""
    d = DATA_DIR / "users" / username
    d.mkdir(parents=True, exist_ok=True)
    return d
