"""Agent authentication, token management, hash indexing and scoped permissions."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import auth
from storage import locked_json_update, read_json_file
from user_paths import DATA_DIR, user_dir

CST = timezone(timedelta(hours=8))
TOKEN_PREFIX = "cda_"
LAST_USED_THROTTLE_SECONDS = 300  # Only update last_used_at once per 5 minutes per token
VALID_SCOPES = frozenset({"read", "write", "delete"})
DEFAULT_NEW_TOKEN_SCOPES = ["read"]
DEFAULT_LEGACY_SCOPES = ["read", "write", "delete"]


def _token_file(username: str) -> Path:
    return user_dir(username) / "agent_token.json"


def _index_file() -> Path:
    return DATA_DIR / "agent_token_index.json"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_tokens_data(data: dict | list, username: str) -> dict:
    """Normalize legacy single-token dict or multi-token format into a unified structure."""
    if not isinstance(data, dict):
        return {"tokens": []}

    tokens = list(data.get("tokens", [])) if isinstance(data.get("tokens"), list) else []

    # Check for legacy single-token format at top level
    legacy_hash = data.get("token_hash")
    if legacy_hash and isinstance(legacy_hash, str) and not any(t.get("token_hash") == legacy_hash for t in tokens):
        tokens.insert(0, {
            "id": "legacy",
            "name": "默认凭据 (Legacy)",
            "token_hash": legacy_hash,
            "account_id": data.get("account_id"),
            "created_at": data.get("created_at"),
            "expires_at": None,
            "scopes": ["read", "write", "delete"],
            "last_used_at": data.get("last_used_at"),
            "revoked": False,
        })

    return {
        "tokens": tokens,
        # Preserve top-level fields for backward compatibility if active tokens exist
        "token_hash": tokens[0]["token_hash"] if tokens and not tokens[0].get("revoked") else None,
        "account_id": tokens[0].get("account_id") if tokens else None,
        "created_at": tokens[0].get("created_at") if tokens else None,
        "last_used_at": tokens[0].get("last_used_at") if tokens else None,
    }


def _update_index_add(token_hash: str, username: str, token_id: str, account_id: str | None) -> None:
    """Add a token mapping to the global hash index."""
    def mutate(index):
        if not isinstance(index, dict):
            index = {}
        index[token_hash] = {
            "username": username,
            "token_id": token_id,
            "account_id": account_id,
        }
        return index

    try:
        locked_json_update(_index_file(), {}, mutate)
    except Exception:
        pass


def _update_index_remove(token_hashes: list[str]) -> None:
    """Remove token mappings from the global hash index."""
    if not token_hashes:
        return

    def mutate(index):
        if not isinstance(index, dict):
            return {}
        for h in token_hashes:
            index.pop(h, None)
        return index

    try:
        locked_json_update(_index_file(), {}, mutate)
    except Exception:
        pass


def rebuild_token_index() -> None:
    """Reconstruct the global token hash index by scanning all user token files."""
    users_dir = DATA_DIR / "users"
    new_index = {}
    for user_path in users_dir.iterdir() if users_dir.exists() else []:
        if not user_path.is_dir():
            continue
        token_path = user_path / "agent_token.json"
        if not token_path.exists():
            continue
        try:
            raw_data = read_json_file(token_path, {})
            normalized = _normalize_tokens_data(raw_data, user_path.name)
            for tok in normalized.get("tokens", []):
                th = tok.get("token_hash")
                if th and not tok.get("revoked"):
                    new_index[th] = {
                        "username": user_path.name,
                        "token_id": tok.get("id"),
                        "account_id": tok.get("account_id"),
                    }
        except Exception:
            continue

    def replace_all(_data):
        return new_index

    locked_json_update(_index_file(), {}, replace_all)


def create_token(
    username: str,
    name: str = "",
    scopes: list[str] | None = None,
    expires_in_days: int | None = None,
) -> str:
    """Generate a new high-entropy Agent API token with specific scopes and optional expiration."""
    with auth.account_operation(username):
        account = auth.account_metadata(username)
        if not account or account.get("status") != "active":
            raise ValueError("account is not active")
        return _create_token(username, name, scopes, expires_in_days)


def _create_token(username, name, scopes, expires_in_days):
    raw_token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    thash = _token_hash(raw_token)
    now = datetime.now(CST)
    now_iso = now.isoformat()
    account = auth.account_metadata(username)
    account_id = account.get("account_id") if account else None

    # Newly issued tokens default to read-only; only legacy records keep full scopes.
    valid_scopes = []
    if scopes is not None:
        for s in scopes:
            s_clean = str(s).strip().lower()
            if s_clean in VALID_SCOPES and s_clean not in valid_scopes:
                valid_scopes.append(s_clean)
        if not valid_scopes:
            valid_scopes = ["read"]
    else:
        valid_scopes = list(DEFAULT_NEW_TOKEN_SCOPES)

    # Expiration
    expires_at = None
    if expires_in_days is not None and isinstance(expires_in_days, int):
        expires_at = (now + timedelta(days=expires_in_days)).isoformat()


    token_id = f"cda_tok_{secrets.token_hex(6)}"
    token_entry = {
        "id": token_id,
        "name": (name or "").strip() or "Agent Token",
        "token_hash": thash,
        "account_id": account_id,
        "created_at": now_iso,
        "expires_at": expires_at,
        "scopes": valid_scopes,
        "last_used_at": None,
        "revoked": False,
    }

    def add_token(data):
        normalized = _normalize_tokens_data(data, username)
        tokens = normalized.get("tokens", [])
        if sum(not t.get('revoked') and (not t.get('expires_at') or str(t['expires_at']) > now_iso) for t in tokens) >= 20:
            raise ValueError('有效 Agent Token 最多 20 个，请先撤销不用的凭据')
        tokens.insert(0, token_entry)
        tokens = [t for t in tokens if not t.get('revoked')] + [t for t in tokens if t.get('revoked')][:100]
        normalized["tokens"] = tokens
        normalized["token_hash"] = thash
        normalized["account_id"] = account_id
        normalized["created_at"] = now_iso
        normalized["last_used_at"] = None
        return normalized

    locked_json_update(_token_file(username), {}, add_token)
    _update_index_add(thash, username, token_id, account_id)
    return raw_token


def revoke_token(username: str, token_id: str | None = None) -> bool:
    """Revoke one specific token (by token_id) or all tokens if token_id is None."""
    path = _token_file(username)
    revoked = {"value": False}
    removed_hashes = []

    def remove_tokens(data):
        normalized = _normalize_tokens_data(data, username)
        tokens = normalized.get("tokens", [])
        for tok in tokens:
            if tok.get("revoked"):
                continue
            if token_id is None or tok.get("id") == token_id:
                tok["revoked"] = True
                revoked["value"] = True
                if tok.get("token_hash"):
                    removed_hashes.append(tok["token_hash"])

        active_tokens = [t for t in tokens if not t.get("revoked")]
        normalized["tokens"] = tokens
        normalized["token_hash"] = active_tokens[0]["token_hash"] if active_tokens else None
        normalized["account_id"] = active_tokens[0].get("account_id") if active_tokens else None
        normalized["created_at"] = active_tokens[0].get("created_at") if active_tokens else None
        normalized["last_used_at"] = active_tokens[0].get("last_used_at") if active_tokens else None
        return normalized

    locked_json_update(path, {}, remove_tokens)
    if removed_hashes:
        _update_index_remove(removed_hashes)
    return revoked["value"]


def get_token_info(username: str) -> dict:
    """Get metadata about the user's active agent tokens without exposing the token hash."""
    raw_data = read_json_file(_token_file(username), {})
    normalized = _normalize_tokens_data(raw_data, username)
    now = datetime.now(CST)

    tokens_list = []
    for t in normalized.get("tokens", []):
        if t.get("revoked"):
            continue
        is_expired = False
        if t.get("expires_at"):
            try:
                exp_dt = datetime.fromisoformat(t["expires_at"])
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=CST)
                is_expired = exp_dt < now
            except (TypeError, ValueError):
                is_expired = True

        tokens_list.append({
            "id": t.get("id"),
            "name": t.get("name", "Agent Token"),
            "created_at": t.get("created_at"),
            "expires_at": t.get("expires_at"),
            "is_expired": is_expired,
            "scopes": t.get("scopes", ["read"]),
            "last_used_at": t.get("last_used_at"),
        })

    has_active = any(not t["is_expired"] for t in tokens_list)
    first_active = next((t for t in tokens_list if not t["is_expired"]), None)
    return {
        "has_token": has_active,
        "created_at": first_active["created_at"] if first_active else None,
        "last_used_at": first_active["last_used_at"] if first_active else None,
        "tokens": tokens_list,
    }


def resolve_token(token: str) -> dict | None:
    """Resolve a raw token via the global hash index, validating expiration, account status, and scopes."""
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if not token.startswith(TOKEN_PREFIX):
        return None

    computed_hash = _token_hash(token)
    index_file = _index_file()

    # Look up in index
    entry = None
    if index_file.exists():
        index_data = read_json_file(index_file, {})
        entry = index_data.get(computed_hash)

    # Invalid tokens must not cause an all-user scan on every request.
    if not index_file.exists():
        rebuild_token_index()
        index_data = read_json_file(index_file, {})
        entry = index_data.get(computed_hash)

    if not entry or not isinstance(entry, dict):
        return None

    username = entry.get("username")
    token_id = entry.get("token_id")
    if not username:
        return None

    # Check account status
    account = auth.account_metadata(username)
    if not account or account.get("status") != "active":
        return None
    if entry.get("account_id") and account.get("account_id") and account.get("account_id") != entry.get("account_id"):
        return None



    # Read user's token file to verify specific token record
    token_file = _token_file(username)
    if not token_file.exists():
        return None

    raw_data = read_json_file(token_file, {})
    normalized = _normalize_tokens_data(raw_data, username)
    matched_tok = None
    for tok in normalized.get("tokens", []):
        if tok.get("revoked"):
            continue
        if tok.get("token_hash") and hmac.compare_digest(tok["token_hash"], computed_hash):
            matched_tok = tok
            break

    if not matched_tok:
        return None

    now = datetime.now(CST)

    # Check expiration
    if matched_tok.get("expires_at"):
        try:
            exp_dt = datetime.fromisoformat(matched_tok["expires_at"])
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=CST)
            if exp_dt < now:
                return None  # Expired
        except (TypeError, ValueError):
            return None

    # Throttle last_used_at update: only write if > LAST_USED_THROTTLE_SECONDS since last record
    last_used_raw = matched_tok.get("last_used_at")
    should_touch = False
    if not last_used_raw:
        should_touch = True
    else:
        try:
            prev_dt = datetime.fromisoformat(last_used_raw)
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=CST)
            if (now - prev_dt).total_seconds() >= LAST_USED_THROTTLE_SECONDS:
                should_touch = True
        except Exception:
            should_touch = True

    if should_touch:
        now_iso = now.isoformat()

        def touch(data):
            norm = _normalize_tokens_data(data, username)
            for t in norm.get("tokens", []):
                if t.get("token_hash") and hmac.compare_digest(t["token_hash"], computed_hash):
                    t["last_used_at"] = now_iso
                    break
            norm["last_used_at"] = now_iso
            return norm

        with auth.account_operation(username):
            current = auth.account_metadata(username)
            if not current or current.get("status") != "active" or current.get("account_id") != account.get("account_id"):
                return None
            locked_json_update(token_file, {}, touch)

    return {
        "username": username,
        "token_id": matched_tok.get("id", token_id),
        "name": matched_tok.get("name", "Agent Token"),
        "scopes": list(matched_tok.get("scopes", ["read"])),
        "token_hash_prefix": computed_hash[:16],
    }


def username_for_token(token: str) -> str | None:
    """Backward-compatible helper returning username for a valid token."""
    res = resolve_token(token)
    return res["username"] if res else None
