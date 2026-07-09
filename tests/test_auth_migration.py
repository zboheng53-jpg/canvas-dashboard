def test_first_registration_moves_zhihuishu_json_files(tmp_path, monkeypatch):
    import auth
    import user_paths

    monkeypatch.setattr(auth, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "SECRET_KEY_FILE", tmp_path / ".flask_secret_key")
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)

    legacy_files = [
        "zhihuishu_state.json",
        "zhihuishu_cache.json",
        "zhihuishu_cookies.json",
    ]
    for name in legacy_files:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    ok, error = auth.register("alice", "password1")

    assert ok is True
    assert error is None
    for name in legacy_files:
        assert not (tmp_path / name).exists()
        assert (tmp_path / "users" / "alice" / name).exists()
