"""First-render OJ behavior while the upstream synchronization is still pending."""
from datetime import timedelta
from threading import Barrier, Event
import time

import pytest
from playwright.sync_api import expect

import platform_sync
import app as dashboard_app
import tongji_oj_client
from storage import read_json_file, write_json_file


def _open_connected_oj(page, live_app, username):
    page.goto(f"{live_app}/register")
    page.fill("#register-username", username)
    page.fill("#register-password", "strong-password")
    page.click("#register-form button")
    page.wait_for_url(f"{live_app}/")
    page.wait_for_function("tongjiojPending === null")
    tongji_oj_client.save_credentials(username, "fake-student", "fake-password")
    platform_sync.mark_connected(username, "tongjioj")


def _item(test_now, title="Cached OJ homework", course="45"):
    return {"id": "tjoj_590", "title": title, "course_id": course, "course": "OJ course",
            "due_ts": (test_now + timedelta(days=3)).isoformat(), "due_str": "07-12", "type": "Homework", "url": ""}


def _response(item=None, **kwargs):
    return {"ok": True, "data": [item] if item else [], "has_cache": True,
            "hidden": [], "highlighted": [], "deleted": [], "courses": [],
            "sync": {"connection_state": "connected", "data_state": "fresh", "refreshing": False}, **kwargs}


@pytest.mark.parametrize("has_cache", [True, False])
def test_oj_displays_cache_or_first_sync_notice_before_slow_response(live_app, browser, test_now, has_cache):
    page = browser.new_page()
    username = f"ojfirst{int(has_cache)}"
    _open_connected_oj(page, live_app, username)
    if has_cache:
        tongji_oj_client.set_selected_course(username, "45")
        tongji_oj_client._save_cache_payload(username, [_item(test_now)], [{"id": "45", "name": "OJ course"}])
        payload = read_json_file(tongji_oj_client._cache_file(username), {})
        payload["updated_at"] = (test_now - timedelta(hours=1)).isoformat()
        write_json_file(tongji_oj_client._cache_file(username), payload)

    pending = []
    page.route("**/api/tongjioj/todos?refresh=1", lambda route: pending.append(route))
    page.reload()
    notice = page.locator("#tongjioj-sync-notice")
    expect(notice).to_contain_text("上次同步" if has_cache else "首次同步")
    if has_cache:
        expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")
        expect(page.locator("#tjoj-course-select-inline")).to_have_value("45")
    page.wait_for_function("tongjiojPending !== null")
    assert len(pending) == 1
    page.click("#btn-refresh")
    page.evaluate("void fetchTongjiojTodos('', true)")
    assert len(pending) == 1

    pending[0].fulfill(json=_response(_item(test_now, "Updated OJ homework")))
    expect(page.locator("#todo-list")).to_contain_text("Updated OJ homework")
    expect(page.locator("#todo-list")).not_to_contain_text("Cached OJ homework")
    expect(notice).to_be_hidden()


@pytest.mark.parametrize("failure", ["network", "http"])
def test_oj_refresh_failure_keeps_homework_and_shows_warning(live_app, browser, test_now, failure):
    page = browser.new_page()
    _open_connected_oj(page, live_app, "ojfailure")
    tongji_oj_client._save_cache_payload("ojfailure", [_item(test_now)], [])
    # This cache is fresh in real server time, so only an explicit refresh contacts OJ.
    pending = []
    page.route("**/api/tongjioj/todos?refresh=1", lambda route: pending.append(route))
    page.reload()
    expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")
    page.wait_for_function("tongjiojPending === null")
    assert not pending
    page.click("#btn-refresh")
    expect(page.locator("#tongjioj-sync-notice")).to_contain_text("正在更新")
    assert len(pending) == 1
    if failure == "network":
        pending[0].abort("failed")
    else:
        pending[0].fulfill(status=503, json={"ok": False, "error": "同步暂不可用"})
    expect(page.locator("#tongjioj-sync-notice")).to_contain_text("更新失败")
    expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")


def test_oj_course_switch_ignores_older_inflight_response(live_app, browser, test_now):
    page = browser.new_page()
    _open_connected_oj(page, live_app, "ojcourses")
    courses = [{"id": "45", "name": "Course A"}, {"id": "46", "name": "Course B"}]
    first = _item(test_now, "Course A cached")
    second = {**_item(test_now, "Course B cached", "46"), "id": "tjoj_591"}
    tongji_oj_client.set_selected_course("ojcourses", "45")
    tongji_oj_client._save_cache_payload("ojcourses", [first, second], courses)
    payload = read_json_file(tongji_oj_client._cache_file("ojcourses"), {})
    payload["updated_at"] = (test_now - timedelta(hours=1)).isoformat()
    write_json_file(tongji_oj_client._cache_file("ojcourses"), payload)
    pending = []
    def route_oj(route):
        if "refresh=1" in route.request.url:
            pending.append(route)
        else:
            route.continue_()
    page.route("**/api/tongjioj/todos?*", route_oj)
    page.reload()
    expect(page.locator("#todo-list")).to_contain_text("Course A cached")
    page.evaluate("document.getElementById('tjoj-course-select-inline').value = '46'; void changeTongjiojCourseInline()")
    expect(page.locator("#todo-list")).to_contain_text("Course B cached")
    assert len(pending) == 2
    pending[1].fulfill(json=_response({**second, "title": "Course B updated"}, courses=courses, selected_course="46"))
    expect(page.locator("#todo-list")).to_contain_text("Course B updated")
    pending[0].fulfill(json=_response({**first, "title": "Course A updated"}, courses=courses, selected_course="45"))
    page.wait_for_function("tongjiojPending === null")
    expect(page.locator("#todo-list")).not_to_contain_text("Course A updated")
    expect(page.locator("#tjoj-course-select-inline")).to_have_value("46")


@pytest.mark.waitress(threads=4)
def test_slow_oj_refresh_leaves_production_request_threads_available(live_app, browser, test_now, monkeypatch):
    page = browser.new_page()
    _open_connected_oj(page, live_app, "ojthreads")
    tongji_oj_client._save_cache_payload("ojthreads", [_item(test_now)], [])
    started, release, finished = Event(), Event(), Event()
    calls = []
    original_worker = tongji_oj_client._run_background_refresh
    def observed_worker(username, job):
        try:
            original_worker(username, job)
        finally:
            finished.set()
    def slow_pages(username):
        calls.append(username)
        started.set()
        assert release.wait(10)
        return "<html><body></body></html>", "<html><body></body></html>", None
    monkeypatch.setattr(tongji_oj_client, "_run_background_refresh", observed_worker)
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_pages", slow_pages)
    try:
        page.reload()
        expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")
        page.wait_for_function("tongjiojPending === null")
        page.click("#btn-refresh")
        assert started.wait(2)
        # Four concurrent slow refreshes previously filled all four Waitress threads.
        page.evaluate("""() => {
            window.ojStressDone = false;
            Promise.all(Array.from({length: 4}, () => fetch('/api/tongjioj/todos?refresh=1').then(r => r.json())))
              .then(results => { window.ojStressDone = results.every(r => r.sync.refreshing); });
        }""")
        clock_started = time.monotonic()
        response = page.request.get(f"{live_app}/api/clock", timeout=2000)
        assert response.ok
        assert time.monotonic() - clock_started < 2
        expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true", timeout=2000)
        page.wait_for_function("window.ojStressDone === true", timeout=2000)
        assert calls == ["ojthreads"]
        expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")
        assert not finished.is_set()  # This evidence is collected while OJ is genuinely blocked.
    finally:
        release.set()
        assert finished.wait(2)
    expect(page.locator("#tongjioj-sync-notice")).to_be_hidden(timeout=5000)
    expect(page.locator("#todo-list")).not_to_contain_text("Cached OJ homework")


@pytest.mark.waitress
def test_refresh_burst_keeps_local_requests_responsive(live_app, browser, monkeypatch):
    page = browser.new_page()
    _open_connected_oj(page, live_app, "refreshburst")
    entered, release = Barrier(7), Event()
    normal_fetch = dashboard_app.fetch_canvas_planner
    def slow_canvas(username):
        entered.wait(timeout=5)
        assert release.wait(5)
        return normal_fetch(username)
    monkeypatch.setattr(dashboard_app, "fetch_canvas_planner", slow_canvas)
    try:
        page.evaluate("""() => {
            window.slowPlatformsDone = false;
            Promise.all(Array.from({length: 6}, () => fetch('/api/canvas/todos').then(r => r.json())))
              .then(() => { window.slowPlatformsDone = true; });
        }""")
        entered.wait(timeout=5)
        started = time.monotonic()
        assert page.request.get(f"{live_app}/api/clock", timeout=2000).ok
        assert page.request.get(f"{live_app}/api/actions", timeout=2000).ok
        assert time.monotonic() - started < 2
    finally:
        release.set()
    page.wait_for_function("window.slowPlatformsDone === true")

