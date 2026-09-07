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
