def test_backoff_caps_at_one_hour():
    from zhihuishu_worker import next_delay_seconds

    assert next_delay_seconds(0) == 15 * 60
    assert next_delay_seconds(1) == 30 * 60
    assert next_delay_seconds(2) == 60 * 60
    assert next_delay_seconds(5) == 60 * 60


def test_dry_run_once_updates_status(tmp_path, monkeypatch):
    import zhihuishu_store
    from zhihuishu_worker import main

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)

    assert main(["--once", "--dry-run", "--username", "alice"]) == 0
    status = zhihuishu_store.load_status("alice")
    assert status["worker"] == "dry_run"


def test_scheduled_cycle_skips_fetch_until_interval(tmp_path, monkeypatch):
    import zhihuishu_store
    import zhihuishu_worker

    calls = []

    class FakeBrowser:
        @staticmethod
        def check_session(username):
            calls.append(("check", username))
            return True

        @staticmethod
        def keepalive(username):
            calls.append(("keepalive", username))
            return True

        @staticmethod
        def fetch_assignments(username):
            calls.append(("fetch", username))
            return [{"id": "zhs_1", "title": "作业"}]

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(zhihuishu_worker, "zhihuishu_browser", FakeBrowser, raising=False)
    zhihuishu_store.save_status("alice", {"last_fetch_at": 1000.0})

    zhihuishu_worker.run_scheduled_cycle("alice", now=1000.0 + 60)

    assert calls == [("check", "alice"), ("keepalive", "alice")]
    assert zhihuishu_store.load_cache("alice")["items"] == []


def test_scheduled_cycle_fetches_after_interval(tmp_path, monkeypatch):
    import zhihuishu_store
    import zhihuishu_worker

    class FakeBrowser:
        @staticmethod
        def check_session(username):
            return True

        @staticmethod
        def keepalive(username):
            return True

        @staticmethod
        def fetch_assignments(username):
            return [{"id": "zhs_1", "title": "作业"}]

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(zhihuishu_worker, "zhihuishu_browser", FakeBrowser, raising=False)
    zhihuishu_store.save_status("alice", {"last_fetch_at": 1000.0})

    zhihuishu_worker.run_scheduled_cycle("alice", now=1000.0 + zhihuishu_worker.FETCH_INTERVAL_SECONDS + 1)

    assert zhihuishu_store.load_cache("alice")["items"][0]["id"] == "zhs_1"
