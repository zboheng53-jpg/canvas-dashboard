"""Agent authentication and token management module."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

import auth
from storage import locked_json_update, read_json_file
from user_paths import DATA_DIR, user_dir

CST = timezone(timedelta(hours=8))
TOKEN_PREFIX = "cda_"


def _token_file(username: str) -> Path:
    return user_dir(username) / "agent_token.json"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(username: str) -> str:
    """Generate a new high-entropy Agent API token for the user, store its hash, and return the raw token."""
    raw_token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    now_iso = datetime.now(CST).isoformat()

    def replace_token(_data):
        return {
            "token_hash": _token_hash(raw_token),
            "created_at": now_iso,
            "last_used_at": None,
        }

    locked_json_update(_token_file(username), {}, replace_token)
    return raw_token


def revoke_token(username: str) -> bool:
    """Revoke the user's Agent API token if present."""
    path = _token_file(username)
    revoked = {"value": False}

    def remove_token(data):
        if data.pop("token_hash", None):
            revoked["value"] = True
        data["created_at"] = None
        data["last_used_at"] = None
        return data

    locked_json_update(path, {}, remove_token)
    return revoked["value"]


def get_token_info(username: str) -> dict:
    """Get metadata about the user's agent token without exposing the token hash."""
    data = read_json_file(_token_file(username), {})
    has_token = bool(data.get("token_hash"))
    return {
        "has_token": has_token,
        "created_at": data.get("created_at") if has_token else None,
        "last_used_at": data.get("last_used_at") if has_token else None,
    }


def username_for_token(token: str) -> str | None:
    """Resolve a raw token to an active username using constant-time hash comparison and touch last_used_at."""
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if not token.startswith(TOKEN_PREFIX):
        return None

    users_dir = DATA_DIR / "users"
    if not users_dir.exists():
        return None

    computed_hash = _token_hash(token)
    matched_user = None

    for user_path in users_dir.iterdir():
        if not user_path.is_dir():
            continue
        token_path = user_path / "agent_token.json"
        if not token_path.exists():
            continue
        stored = read_json_file(token_path, {}).get("token_hash")
        if stored and hmac.compare_digest(stored, computed_hash):
            matched_user = user_path.name
            break

    if not matched_user:
        return None

    # Check account active status
    account = auth.account_metadata(matched_user)
    if account and account.get("status") != "active":
        return None

    # Touch last_used_at safely
    now_iso = datetime.now(CST).isoformat()

    def touch(data):
        if data.get("token_hash"):
            data["last_used_at"] = now_iso
        return data

    try:
        locked_json_update(_token_file(matched_user), {}, touch)
    except Exception:
        pass

    return matched_user
