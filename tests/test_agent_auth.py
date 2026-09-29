import json
from datetime import datetime, timezone, timedelta
import pytest

import agent_auth


def test_agent_token_creation_storage_and_validation(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    (users_dir / "alice").mkdir(parents=True)
    (users_dir / "bob").mkdir(parents=True)

    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth, "user_dir", lambda username: users_dir / username)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})

    # Create token for Alice and Bob
    alice_token = agent_auth.create_token("alice")
    bob_token = agent_auth.create_token("bob")

    assert alice_token.startswith("cda_")
    assert bob_token.startswith("cda_")
    assert alice_token != bob_token

    # Verify storage contains hash, not raw token
    stored_alice = json.loads((users_dir / "alice" / "agent_token.json").read_text(encoding="utf-8"))
    assert "token_hash" in stored_alice
    assert alice_token not in stored_alice.values()
    assert stored_alice["created_at"] is not None
    assert stored_alice["last_used_at"] is None

    # Verify metadata retrieval
    info = agent_auth.get_token_info("alice")
    assert info["has_token"] is True
    assert info["created_at"] == stored_alice["created_at"]
    assert info["last_used_at"] is None

    # Validate resolution
    assert agent_auth.username_for_token(alice_token) == "alice"
    assert agent_auth.username_for_token(bob_token) == "bob"
    assert agent_auth.username_for_token("invalid_token") is None
    assert agent_auth.username_for_token("") is None

    # Touch test: verify last_used_at is updated after validation
    info_updated = agent_auth.get_token_info("alice")
    assert info_updated["last_used_at"] is not None


def test_agent_token_revocation(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    (users_dir / "alice").mkdir(parents=True)
    (users_dir / "bob").mkdir(parents=True)

    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth, "user_dir", lambda username: users_dir / username)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})

    alice_token = agent_auth.create_token("alice")
    bob_token = agent_auth.create_token("bob")

    assert agent_auth.revoke_token("alice") is True
    assert agent_auth.username_for_token(alice_token) is None
    assert agent_auth.username_for_token(bob_token) == "bob"
    assert agent_auth.revoke_token("alice") is False

    info = agent_auth.get_token_info("alice")
    assert info["has_token"] is False
    assert info["created_at"] is None


def test_agent_multi_tokens_scopes_and_expiration(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    (users_dir / "alice").mkdir(parents=True)

    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth, "user_dir", lambda username: users_dir / username)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})

    # 1. Create token with name, scopes, and expiration
    tok1 = agent_auth.create_token("alice", name="Desktop", scopes=["read"], expires_in_days=30)
    tok2 = agent_auth.create_token("alice", name="CLI", scopes=["read", "write", "delete"])
    tok_expired = agent_auth.create_token("alice", name="Old", expires_in_days=-1)

    info = agent_auth.get_token_info("alice")
    assert len(info["tokens"]) == 3
    assert info["tokens"][0]["name"] == "Old"
    assert info["tokens"][0]["is_expired"] is True
    assert info["tokens"][1]["name"] == "CLI"
    assert set(info["tokens"][1]["scopes"]) == {"read", "write", "delete"}
    assert info["tokens"][2]["name"] == "Desktop"
    assert info["tokens"][2]["scopes"] == ["read"]

    # Resolution
    res1 = agent_auth.resolve_token(tok1)
    assert res1 is not None
    assert res1["username"] == "alice"
    assert res1["scopes"] == ["read"]

    res2 = agent_auth.resolve_token(tok2)
    assert res2 is not None
    assert set(res2["scopes"]) == {"read", "write", "delete"}

    # Expired token cannot resolve
    assert agent_auth.resolve_token(tok_expired) is None

    # Single token revocation
    tok2_id = res2["token_id"]
    assert agent_auth.revoke_token("alice", token_id=tok2_id) is True
    assert agent_auth.resolve_token(tok2) is None
    # tok1 is still active
    assert agent_auth.resolve_token(tok1) is not None


def test_agent_token_last_used_throttling_and_index(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    (users_dir / "alice").mkdir(parents=True)

    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth, "user_dir", lambda username: users_dir / username)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})

    token = agent_auth.create_token("alice")
    # Verify index exists
    index_file = tmp_path / "agent_token_index.json"
    assert index_file.exists()
    index_data = json.loads(index_file.read_text(encoding="utf-8"))
    thash = agent_auth._token_hash(token)
    assert thash in index_data
    assert index_data[thash]["username"] == "alice"

    # First resolve touches last_used_at
    res = agent_auth.resolve_token(token)
    assert res is not None
    tok_file = users_dir / "alice" / "agent_token.json"
    data1 = json.loads(tok_file.read_text(encoding="utf-8"))
    last_used_1 = data1["tokens"][0]["last_used_at"]
    assert last_used_1 is not None

    # Immediate second resolve should be throttled (no re-write to disk)
    res2 = agent_auth.resolve_token(token)
    assert res2 is not None
    data2 = json.loads(tok_file.read_text(encoding="utf-8"))
    assert data2["tokens"][0]["last_used_at"] == last_used_1

    # Test index deletion and automatic rebuild
    index_file.unlink()
    assert not index_file.exists()
    res3 = agent_auth.resolve_token(token)
    assert res3 is not None
    assert index_file.exists()


def test_agent_legacy_format_backward_compatibility(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    (users_dir / "alice").mkdir(parents=True)

    monkeypatch.setattr(agent_auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(agent_auth, "user_dir", lambda username: users_dir / username)
    monkeypatch.setattr(agent_auth.auth, "account_metadata", lambda username: {"status": "active"})

    raw_token = "cda_legacytoken12345678901234567890"
    thash = agent_auth._token_hash(raw_token)
    # Write legacy single-token format
    tok_file = users_dir / "alice" / "agent_token.json"
    tok_file.write_text(json.dumps({
        "token_hash": thash,
        "account_id": "acc-123",
        "created_at": "2026-09-01T12:00:00+08:00",
        "last_used_at": None,
    }), encoding="utf-8")

    # Rebuild index to pick up legacy token
    agent_auth.rebuild_token_index()

    # Legacy token resolves successfully with full permissions
    res = agent_auth.resolve_token(raw_token)
    assert res is not None
    assert res["username"] == "alice"
    assert set(res["scopes"]) == {"read", "write", "delete"}

    # Legacy token is not quietly revoked
    info = agent_auth.get_token_info("alice")
    assert info["has_token"] is True
    assert len(info["tokens"]) == 1
    assert set(info["tokens"][0]["scopes"]) == {"read", "write", "delete"}
