import time


def test_status_defaults_to_never_logged_in(tmp_path, monkeypatch):
    import zhihuishu_store

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    status = zhihuishu_store.load_status("alice")

    assert status["session"] == "not_logged_in"
    assert status["worker"] == "unknown"
    assert status["last_success_at"] is None


def test_cache_round_trip_marks_stale(tmp_path, monkeypatch):
    import zhihuishu_store

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    zhihuishu_store.save_cache(
        "alice",
        [{"id": "zhs_1", "title": "作业"}],
        fetched_at=time.time() - 7200,
    )

    cache = zhihuishu_store.load_cache("alice", stale_after_seconds=1800)

    assert cache["items"][0]["id"] == "zhs_1"
    assert cache["stale"] is True


def test_state_update_is_string_based(tmp_path, monkeypatch):
    import zhihuishu_store

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    state = zhihuishu_store.update_state("alice", "hide", "zhs_1")
    assert state["hidden"] == ["zhs_1"]

    state = zhihuishu_store.update_state("alice", "delete", "zhs_1")
    assert state["hidden"] == []
    assert state["deleted"] == ["zhs_1"]
