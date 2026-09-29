"""Pre-launch capacity guard: admission thresholds, fail-closed behaviour and the public page.

The guard must close new registrations *before* parallel work can exhaust the
single Web process, and it must never claim there is room left when it cannot
read the metrics it depends on.
"""
from datetime import datetime, timedelta

import auth
import capacity_guard
import platform_sync
import settings


def _limits(monkeypatch, *, total=15, active=10, platforms=40):
    monkeypatch.setattr(settings, "CAPACITY_MAX_TOTAL_USERS", total)
    monkeypatch.setattr(settings, "CAPACITY_MAX_ACTIVE_USERS", active)
    monkeypatch.setattr(settings, "CAPACITY_MAX_CONNECTED_PLATFORMS", platforms)
    capacity_guard.reset_cache()


def _make_users(count, prefix="member"):
    for index in range(count):
        assert auth.register(f"{prefix}{index}", "password1")[0]


def test_total_user_threshold_closes_registration(isolated_data, monkeypatch):
    _limits(monkeypatch, total=3, active=0, platforms=0)
    _make_users(2)
    assert capacity_guard.evaluate().registration_open

    _make_users(1, prefix="extra")

    decision = capacity_guard.evaluate(force=True)
    assert decision.registration_open is False
    assert decision.reason == capacity_guard.REASON_TOTAL_USERS
    assert decision.metrics["total_users"] == 3


def test_active_user_threshold_counts_recent_logins(isolated_data, monkeypatch):
    _limits(monkeypatch, total=0, active=2, platforms=0)
    _make_users(3)

    decision = capacity_guard.evaluate(force=True)
    assert decision.reason == capacity_guard.REASON_ACTIVE_USERS
    assert decision.metrics["active_users"] == 3


def test_active_window_ignores_stale_login_but_counts_presence(isolated_data, monkeypatch):
    _limits(monkeypatch, total=0, active=1, platforms=0)
    auth.register("member0", "password1")
    later = datetime.now(capacity_guard.CST) + timedelta(days=settings.CAPACITY_ACTIVE_WINDOW_DAYS + 5)

    stale = capacity_guard.evaluate(now=later, force=True)
    assert stale.metrics["active_users"] == 0
    assert stale.registration_open is True

    assert capacity_guard.remember_activity("member0", now=later) is True
    assert capacity_guard.remember_activity("member0", now=later) is False  # throttled

    fresh = capacity_guard.evaluate(now=later + timedelta(minutes=5), force=True)
    assert fresh.metrics["active_users"] == 1
    assert fresh.reason == capacity_guard.REASON_ACTIVE_USERS


def test_connected_platform_threshold_closes_registration(isolated_data, monkeypatch):
    _limits(monkeypatch, total=0, active=0, platforms=2)
    auth.register("member0", "password1")
    platform_sync.mark_connected("member0", "canvas")
    assert capacity_guard.evaluate(force=True).registration_open

    platform_sync.mark_connected("member0", "haoke")

    decision = capacity_guard.evaluate(force=True)
    assert decision.reason == capacity_guard.REASON_CONNECTED_PLATFORMS
    assert decision.metrics["connected_platforms"] == 2


def test_zero_threshold_disables_only_that_gate(isolated_data, monkeypatch):
    _limits(monkeypatch, total=0, active=0, platforms=0)
    _make_users(18)

    assert capacity_guard.evaluate(force=True).registration_open is True


def test_disabled_guard_keeps_registration_open(isolated_data, monkeypatch):
    _limits(monkeypatch, total=1, active=1, platforms=1)
    monkeypatch.setattr(settings, "CAPACITY_GUARD_ENABLED", False)
    _make_users(2)

    decision = capacity_guard.evaluate(force=True)
    assert decision.registration_open is True
    assert decision.metrics is None


def test_manual_pause_keeps_its_own_reason(isolated_data, monkeypatch):
    _limits(monkeypatch, total=0, active=0, platforms=0)
    monkeypatch.setattr(settings, "REGISTRATION_ENABLED", False)

    decision = capacity_guard.evaluate(force=True)
    assert decision.manual_pause is True
    assert decision.reason == capacity_guard.REASON_MANUAL

    notice = capacity_guard.registration_notice(decision)
    assert "暂时停止新注册" in notice["paragraphs"][0]
    assert "仍可正常登录" in notice["note"]


def test_unreadable_registry_fails_closed(isolated_data, monkeypatch):
    _limits(monkeypatch, total=15, active=10, platforms=40)
    (isolated_data / "users.json").write_text("{not json", encoding="utf-8")

    decision = capacity_guard.evaluate(force=True)
    assert decision.registration_open is False
    assert decision.reason == capacity_guard.REASON_CHECK_FAILED
    assert list(isolated_data.glob("users.json.corrupt-*"))


def test_raising_the_limit_after_remediation_reopens_registration(isolated_data, monkeypatch):
    _limits(monkeypatch, total=1, active=0, platforms=0)
    auth.register("member0", "password1")
    assert capacity_guard.evaluate(force=True).registration_open is False

    monkeypatch.setattr(settings, "CAPACITY_MAX_TOTAL_USERS", 5)

    assert capacity_guard.evaluate(force=True).registration_open is True


def test_state_record_is_username_free(isolated_data, monkeypatch):
    _limits(monkeypatch, total=1, active=0, platforms=0)
    auth.register("member0", "password1")

    capacity_guard.evaluate(force=True)

    record = (isolated_data / capacity_guard.STATE_FILE).read_text(encoding="utf-8")
    assert "member0" not in record
    assert capacity_guard.REASON_TOTAL_USERS in record


def test_diagnostics_scans_other_accounts_inside_an_identity_scope(isolated_data, monkeypatch):
    """The aggregate scan must not trip the per-account identity guard."""
    _limits(monkeypatch, total=15, active=10, platforms=40)
    _make_users(2)

    with auth.identity_scope("member0", auth.session_identity("member0")):
        snapshot = capacity_guard.diagnostics()

    assert snapshot["metrics"]["total_users"] == 2
    assert snapshot["registration_open"] is True
    assert snapshot["guard_enabled"] is True


def test_closed_registration_page_and_api(isolated_data, monkeypatch):
    import app

    _limits(monkeypatch, total=1, active=0, platforms=0)
    auth.register("member0", "password1")
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["_csrf_token"] = "test"

    page = client.get("/register").get_data(as_text=True)
    assert 'id="register-closed-notice"' in page
    assert 'id="register-form"' not in page
    assert "用户上限" in page
    assert "谢谢你的期待与谅解" in page
    assert "暂时停止新注册" in page
    assert "auth-landing-hero" in page  # the left showcase is unchanged
    assert "auth-landing-intro" in page

    login_page = client.get("/login").get_data(as_text=True)
    assert 'id="login-form"' in login_page
    assert "新注册暂时关闭" in login_page

    response = client.post(
        "/api/auth/register",
        json={"username": "newcomer", "password": "strong-password"},
        headers={"X-CSRF-Token": "test"},
    )
    assert response.status_code == 403
    assert response.json["code"] == "registration_closed"
    assert response.json["reason"] == capacity_guard.REASON_TOTAL_USERS
    assert "用户上限" in response.json["error"]
    assert auth.user_exists("newcomer") is False
