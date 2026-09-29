import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

import auth
import canvas_auth
import external_subtasks
import haoke_client
import ketangpai_client
import platform_state
import schedule_store
import services.workspace as workspace_service
import zhixuemeng_client
from user_paths import user_dir

CST = timezone(timedelta(hours=8))


def _register_user(username="alice", password="password123"):
    ok, error = auth.register(username, password)
    assert ok, f"register failed: {error}"
    return username


class TestConfigTransactions:
    """Item 1: Concurrent configuration saves must not overwrite each other."""

    def test_concurrent_platform_config_saves_preserve_all_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(canvas_auth, "validate_feed_url", lambda _: (True, None))
        user = _register_user("bob_cfg")
        errors = []

        def save_canvas():
            try:
                ok, err = canvas_auth.save_feed_url(user, "https://canvas.example.edu/feed.ics")
                if not ok:
                    errors.append(f"canvas error: {err}")
            except Exception as e:
                errors.append(f"canvas exc: {e}")

        def save_haoke():
            try:
                haoke_client.save_credentials(user, "hk_user_1", "hk_pass_1")
            except Exception as e:
                errors.append(f"haoke exc: {e}")

        def save_ktp():
            try:
                ketangpai_client._save_token(user, "ktp_token_123")
            except Exception as e:
                errors.append(f"ktp exc: {e}")

        def save_zxm():
            try:
                zhixuemeng_client._save_token(user, "zxm_token_456")
                zhixuemeng_client.save_selected_course(user, "COURSE_CHEM")
            except Exception as e:
                errors.append(f"zxm exc: {e}")

        # Run them in parallel threads
        threads = [
            threading.Thread(target=save_canvas),
            threading.Thread(target=save_haoke),
            threading.Thread(target=save_ktp),
            threading.Thread(target=save_zxm),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent save: {errors}"

        # Verify all fields coexist in config.json
        cfg = haoke_client.read_json_file(user_dir(user) / "config.json", {})
        assert cfg.get("calendar_feed_url") == "https://canvas.example.edu/feed.ics"
        assert cfg.get("haoke_username") == "hk_user_1"
        assert cfg.get("haoke_password_encrypted") is not None
        assert cfg.get("ketangpai_token_encrypted") is not None
        assert cfg.get("zhixuemeng_token_encrypted") is not None
        assert cfg.get("zhixuemeng_selected_course") == "COURSE_CHEM"

        # Now clear one platform, ensure others are preserved
        haoke_client.clear_credentials(user)
        cfg_after = haoke_client.read_json_file(user_dir(user) / "config.json", {})
        assert cfg_after.get("haoke_username") is None
        assert cfg_after.get("calendar_feed_url") == "https://canvas.example.edu/feed.ics"
        assert cfg_after.get("zhixuemeng_selected_course") == "COURSE_CHEM"


class TestPlatformStateDatesAndNoSnapshotOverwrite:
    """Item 2 & 8: Date comparisons (naive vs aware, pure dates, overrides) and snapshot overwrite prevention."""

    def test_naive_due_ts_comparison_does_not_crash(self):
        # Repro for Item 8: naive due_ts vs aware now raised TypeError
        now = datetime(2026, 7, 9, 12, 0, tzinfo=CST)
        state = {"hidden": ["item_naive"], "highlighted": [], "deleted": [], "completed": [], "overrides": {}}
        result = {
            "ok": True,
            "data": [
                {"id": "item_naive", "due_ts": "2026-07-09T10:00:00"},  # naive!
            ],
        }
        # Should not raise TypeError: can't compare offset-naive and offset-aware datetimes
        resp = platform_state.build_platform_todos_response(
            result, state, now=now, auto_delete_expired_hidden=True
        )
        assert "item_naive" in resp["deleted"]

    def test_overridden_due_date_prevents_premature_auto_delete(self):
        # Repro for Item 8: original due_ts is past, but user locally rescheduled to future
        now = datetime(2026, 7, 9, 12, 0, tzinfo=CST)
        state = {
            "hidden": ["item_rescheduled"],
            "highlighted": [],
            "deleted": [],
            "completed": [],
            "overrides": {
                "item_rescheduled": {"due_ts": "2026-07-15T12:00:00+08:00"}
            },
        }
        result = {
            "ok": True,
            "data": [
                {"id": "item_rescheduled", "due_ts": "2026-07-08T12:00:00+08:00"},  # past upstream
            ],
        }
        resp = platform_state.build_platform_todos_response(
            result, state, now=now, auto_delete_expired_hidden=True
        )
        # Must NOT be deleted because overridden due_ts is in future!
        assert "item_rescheduled" in resp["hidden"]
        assert "item_rescheduled" not in resp["deleted"]

    def test_pure_date_due_date_not_expired_during_the_day(self):
        # Repro for Item 8: pure date "2026-07-09" at noon on 2026-07-09 is still due today
        now = datetime(2026, 7, 9, 12, 0, tzinfo=CST)
        state = {"hidden": ["item_today"], "highlighted": [], "deleted": [], "completed": [], "overrides": {}}
        result = {
            "ok": True,
            "data": [
                {"id": "item_today", "due_ts": "2026-07-09"},
            ],
        }
        resp = platform_state.build_platform_todos_response(
            result, state, now=now, auto_delete_expired_hidden=True
        )
        assert "item_today" in resp["hidden"]
        assert "item_today" not in resp["deleted"]

    def test_auto_delete_expired_does_not_overwrite_concurrent_update(self, tmp_path):
        # Repro for Item 2: GET response with auto_delete must not wipe concurrent state changes
        user = _register_user("alice_state")
        store = platform_state.PlatformStateStore(lambda u: user_dir(u) / "test_state.json", str)

        # User has an expired hidden item and an active item
        store.update(user, "hide", "item_old")

        # Concurrently, user marks "item_active" as completed
        # While build_platform_todos_response is running
        now = datetime(2026, 7, 9, 12, 0, tzinfo=CST)
        raw_items = [
            {"id": "item_old", "due_ts": "2026-07-01T12:00:00+08:00"},
            {"id": "item_active", "due_ts": "2026-07-20T12:00:00+08:00"},
        ]

        # If we use delete_expired_hidden instead of full save_state
        initial_state = store.load(user)
        # Simulate concurrent complete between load and build
        store.update(user, "complete", "item_active")

        # Now simulate delta cleanup
        store.delete_expired_hidden(user, ["item_old"])
        final_state = store.load(user)
        assert "item_active" in final_state["completed"], "Concurrent completion was overwritten!"
        assert "item_old" in final_state["deleted"]
        assert "item_old" not in final_state["hidden"]


class TestCanvasStableIdAndMigration:
    """Item 9: Canvas stable ID differentiation and full state/subtasks migration."""

    def test_extract_stable_id_distinguishes_assignment_and_calendar_event(self):
        # Repro for Item 9: assignment_42 vs calendar_event_42 must have distinct IDs
        id_assign = canvas_auth._extract_stable_id(
            "https://canvas.example.edu/courses/1/assignments/42#assignment_42", "uid1"
        )
        id_event = canvas_auth._extract_stable_id(
            "https://canvas.example.edu/courses/1/calendar_events/42#calendar_event_42", "uid2"
        )
        assert id_assign != id_event
        assert str(id_assign) != str(id_event)

    def test_migration_from_cache_migrates_all_state_and_subtasks(self, tmp_path, monkeypatch):
        user = _register_user("canvas_mig")
        udir = user_dir(user)

        # Setup legacy cache with integer/hash IDs
        legacy_cache = [
            {
                "id": 42,
                "title": "Assignment 42",
                "url": "https://canvas.example.edu/courses/1/assignments/42#assignment_42",
                "due_ts": "2026-10-01T12:00:00+08:00",
            },
            {
                "id": 99,
                "title": "Event 99",
                "url": "https://canvas.example.edu/courses/1/calendar_events/99#calendar_event_99",
                "due_ts": "2026-10-02T12:00:00+08:00",
            },
        ]
        storage_write = canvas_auth.write_json_file
        storage_write(udir / "canvas_cache.json", legacy_cache)

        # Setup legacy state: 42 is completed and overridden; 99 is hidden
        legacy_state = {
            "hidden": [99],
            "highlighted": [],
            "deleted": [],
            "completed": [42],
            "overrides": {"42": {"title": "Overridden 42"}},
        }
        storage_write(udir / "canvas_state.json", legacy_state)

        # Setup legacy external subtasks for canvas:42
        external_subtasks.save_subtasks(user, "canvas", 42, [{"text": "Sub 1", "done": False}])

        # Trigger migration
        canvas_auth._migrate_state_from_cache(user)

        new_assign_id = canvas_auth._extract_stable_id(legacy_cache[0]["url"], "uid")
        new_event_id = canvas_auth._extract_stable_id(legacy_cache[1]["url"], "uid")

        state = canvas_auth.load_state(user)
        # Completed, hidden, and overrides must be preserved under new IDs
        assert new_assign_id in state["completed"] or str(new_assign_id) in [str(x) for x in state["completed"]]
        assert new_event_id in state["hidden"] or str(new_event_id) in [str(x) for x in state["hidden"]]
        assert str(new_assign_id) in state["overrides"]
        assert state["overrides"][str(new_assign_id)]["title"] == "Overridden 42"

        # Subtasks must be preserved under new ID
        subtasks = external_subtasks.load_subtasks(user, "canvas", new_assign_id)
        assert len(subtasks) == 1
        assert subtasks[0]["text"] == "Sub 1"


@pytest.fixture
def client():
    import app as dashboard_app
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as c:
        yield c


def _csrf(c, token="csrf-token-123"):
    with c.session_transaction() as sess:
        sess["_csrf_token"] = token
    return {"X-CSRF-Token": token}


class TestAccountDeletionZeroSideEffects:
    """Item 3: Account deletion with wrong password or confirmation must have zero side effects."""

    def test_invalid_account_delete_does_not_disconnect_platforms_or_stop_sessions(self, client, monkeypatch):
        user = "del_tester"
        _register_user(user, "valid_pass_123")

        # Set up a platform credential in user's config.json
        cfg_file = user_dir(user) / "config.json"
        canvas_auth.write_json_file(cfg_file, {
            "calendar_feed_url": "https://canvas.example.edu/feed.ics",
            "haoke_username": "hk_user",
            "haoke_password_encrypted": "dummy",
        })

        # Track if any stop_session or logout was called
        calls = []
        import zhihuishu_login_sessions
        import tongji_login_sessions
        monkeypatch.setattr(zhihuishu_login_sessions, "stop_session", lambda u: calls.append(f"zhs_stop:{u}"))
        monkeypatch.setattr(tongji_login_sessions, "stop_session", lambda u: calls.append(f"tongji_stop:{u}"))

        with client.session_transaction() as sess:
            sess["username"] = user
            account_id, session_version = auth.session_identity(user)
            sess["account_id"] = account_id
            sess["session_version"] = session_version

        csrf_hdr = _csrf(client)

        # 1. Test with WRONG PASSWORD
        res1 = client.delete("/api/account", json={"password": "wrong_password", "confirmation": auth.DELETE_CONFIRMATION}, headers=csrf_hdr)
        assert res1.status_code == 400
        assert not calls, f"Side effects triggered on wrong password: {calls}"
        assert (user_dir(user) / "config.json").exists()
        cfg1 = canvas_auth.read_json_file(cfg_file, {})
        assert cfg1.get("haoke_username") == "hk_user"
        assert cfg1.get("calendar_feed_url") == "https://canvas.example.edu/feed.ics"

        # 2. Test with WRONG CONFIRMATION
        res2 = client.delete("/api/account", json={"password": "valid_pass_123", "confirmation": "wrong_text"}, headers=csrf_hdr)
        assert res2.status_code == 400
        assert not calls, f"Side effects triggered on wrong confirmation: {calls}"
        cfg2 = canvas_auth.read_json_file(cfg_file, {})
        assert cfg2.get("haoke_username") == "hk_user"

        # 3. Test with MISSING FIELDS
        res3 = client.delete("/api/account", json={}, headers=csrf_hdr)
        assert res3.status_code == 400
        assert not calls, f"Side effects triggered on missing fields: {calls}"
        cfg3 = canvas_auth.read_json_file(cfg_file, {})
        assert cfg3.get("haoke_username") == "hk_user"

        # 4. Now perform valid deletion: must succeed and call stops
        res4 = client.delete("/api/account", json={"password": "valid_pass_123", "confirmation": auth.DELETE_CONFIRMATION}, headers=csrf_hdr)
        assert res4.status_code == 200
        assert f"zhs_stop:{user}" in calls
        assert f"tongji_stop:{user}" in calls


class TestAccountDirectoryIsolationAndReregistration:
    """Item 4: User directory isolation into quarantine on delete, and clean re-registration."""

    def test_account_delete_quarantines_directory_and_reregistration_is_clean(self, monkeypatch):
        user = "reuse_user"
        _register_user(user, "pwd123456")
        udir = user_dir(user)
        # Write some user data
        secret_file = udir / "my_secret_note.txt"
        secret_file.write_text("old_user_private_data", encoding="utf-8")

        # Simulate rmtree failing during delete (e.g. file lock on Windows)
        orig_rmtree = shutil.rmtree
        def fail_quarantine_rmtree(path, *args, **kwargs):
            if ".quarantine" in str(path) or "quarantine" in str(path):
                raise PermissionError("Simulated file in use in quarantine")
            return orig_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(shutil, "rmtree", fail_quarantine_rmtree)

        ok, err = auth.delete_account(user, "pwd123456", auth.DELETE_CONFIRMATION)
        assert ok, f"Delete failed: {err}"

        # The user's active directory in users/ must NOT exist anymore!
        active_user_path = auth.DATA_DIR / "users" / user
        assert not active_user_path.exists(), "Active user directory still exists in users/!"

        # Now re-register the same username!
        monkeypatch.undo()
        ok_reg, err_reg = auth.register(user, "new_password_999")
        assert ok_reg, f"Re-register failed: {err_reg}"

        # The new user's directory must be completely clean and not contain the old secret note!
        new_udir = user_dir(user)
        assert not (new_udir / "my_secret_note.txt").exists(), "Old user data leaked to re-registered user!"


class TestAuthIdentityVersionRace:
    """Item 5: Password verification and session issuance must not race with account modification."""

    def test_session_issuance_rejects_stale_identity_after_password_change_or_revoke(self, client, monkeypatch):
        user = "race_user"
        _register_user(user, "initial_password")

        # Hook into auth.verify_login to pause and change password concurrently
        orig_verify_login = auth.verify_login
        stage = {"paused": True, "mutated": False}

        def paused_verify_login(username, password):
            result = orig_verify_login(username, password)
            if username == user and result and stage["paused"]:
                # In between verification and session issuance:
                # User changes password (or revokes sessions) in another thread/session
                auth.change_password(user, "initial_password", "new_super_password")
                stage["mutated"] = True
            return result

        monkeypatch.setattr(auth, "verify_login", paused_verify_login)

        csrf_hdr = _csrf(client)
        # Attempt login with the old password
        res = client.post("/api/auth/login", json={"username": user, "password": "initial_password"}, headers=csrf_hdr)
        assert stage["mutated"] is True
        # The login attempt MUST BE REJECTED because the account version/identity changed
        assert res.status_code == 401
