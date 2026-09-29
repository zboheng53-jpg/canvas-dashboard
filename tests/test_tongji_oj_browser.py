"""First-render OJ behavior while the upstream synchronization is still pending."""
from datetime import timedelta
from threading import Barrier, Event
import os
import time

import pytest
from playwright.sync_api import expect

import platform_sync
import haoke_client
import app as dashboard_app
import external_subtasks
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


@pytest.mark.parametrize("completed", [True, False])
def test_oj_manual_completion_and_undo_survive_cache_upgrade_and_refresh(live_app, browser, test_now, monkeypatch, completed):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    username = f"ojmanual{int(completed)}"
    _open_connected_oj(page, live_app, username)
    title = "Manual OJ homework"
    due = (test_now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<h2 data-id="45"><a>45: OJ course</a></h2><div id="course45">
      <table class="sharif_table"><tr><td>{title}</td><td>Default</td>
      <td><a href="/index.php/assignments/problems_list/590">2 problems</a></td>
      <td>999 submissions</td><td>100%</td><td></td><td>{due}</td><td>Open</td></tr></table></div>"""
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", lambda username: (html, None))
    write_json_file(tongji_oj_client._cache_file(username), {
        "version": 2, "items": [_item(test_now, title)], "courses": [], "updated_at": test_now.isoformat(),
    })
    tongji_oj_client.update_state(username, "complete", "tjoj_590")
    if not completed:
        tongji_oj_client.update_state(username, "uncomplete", "tjoj_590")
    external_subtasks.save_subtasks(username, "tongjioj", "tjoj_590", [
        {"id": 1, "text": "Preserved OJ step", "done": True, "due_date": None},
    ])

    row = page.locator(".todo-row-wrap").filter(has_text=title)
    def expect_completion(expected):
        expect(row).to_be_visible()
        action = row.locator(".item-desktop-actions .btn-dismiss")
        expect(action).to_have_attribute("title", "取消完成" if expected else "完成")
    page.reload()
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true", timeout=5000)
    expect_completion(completed)
    row.locator(".subtask-toggle").click()
    expect(row.locator(".subtask-text")).to_have_text("Preserved OJ step")
    expect(row.locator(".todo-subtask-row input[type=checkbox]")).to_be_checked()

    with page.expect_response("**/api/tongjioj/state"):
        row.locator(".item-desktop-actions .btn-dismiss").click()
    expect_completion(not completed)
    with page.expect_request("**/api/tongjioj/todos?refresh=1"):
        page.click("#btn-refresh")
    page.wait_for_function("tongjiojPending === null")
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true", timeout=5000)
    page.reload()
    expect_completion(not completed)
    with page.expect_response("**/api/tongjioj/state"):
        row.locator(".item-desktop-actions .btn-dismiss").click()
    expect_completion(completed)
    page.reload()
    expect_completion(completed)
    row.locator(".subtask-toggle").click()
    expect(row.locator(".subtask-text")).to_have_text("Preserved OJ step")
    expect(row.locator(".todo-subtask-row input[type=checkbox]")).to_be_checked()


@pytest.mark.parametrize("has_cache", [True, False])
def test_oj_keeps_update_in_refresh_icon_before_slow_response(live_app, browser, test_now, has_cache):
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
    with page.expect_request("**/api/tongjioj/todos?refresh=1"):
        page.reload()
    expect(page.locator("#tongjioj-sync-notice")).to_have_count(0)
    expect(page.locator("#btn-refresh")).to_have_attribute("aria-busy", "true")
    expect(page.locator("#list-updated")).to_be_hidden()
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
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true")
    expect(page.locator("#list-updated")).to_be_hidden()


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
    with page.expect_request("**/api/tongjioj/todos?refresh=1"):
        page.click("#btn-refresh")
    expect(page.locator("#btn-refresh")).to_have_attribute("aria-busy", "true")
    assert len(pending) == 1
    if failure == "network":
        pending[0].abort("failed")
    else:
        pending[0].fulfill(status=503, json={"ok": False, "error": "同步暂不可用"})
    expect(page.locator("#list-updated")).to_have_text("1 处未同步")
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true")
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
    def slow_assignments(username):
        calls.append(username)
        started.set()
        assert release.wait(10)
        return "<html><body></body></html>", None
    monkeypatch.setattr(tongji_oj_client, "_run_background_refresh", observed_worker)
    monkeypatch.setattr(tongji_oj_client, "_fetch_authenticated_assignments", slow_assignments)
    try:
        page.reload()
        expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")
        page.wait_for_function("tongjiojPending === null")
        page.wait_for_function("Object.values(platformRequests).every(count => count === 0) && workspaceRefreshing === false")
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
        expect(page.locator("#btn-refresh")).to_have_attribute("aria-busy", "true", timeout=2000)
        page.wait_for_function("window.ojStressDone === true", timeout=2000)
        assert calls == ["ojthreads"]
        expect(page.locator("#todo-list")).to_contain_text("Cached OJ homework")
        assert not finished.is_set()  # This evidence is collected while OJ is genuinely blocked.
    finally:
        release.set()
        assert finished.wait(2)
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true", timeout=5000)
    expect(page.locator("#list-updated")).to_be_hidden()
    expect(page.locator("#todo-list")).not_to_contain_text("Cached OJ homework")


@pytest.mark.waitress
def test_refresh_burst_keeps_local_requests_responsive(live_app, browser, monkeypatch):
    page = browser.new_page()
    _open_connected_oj(page, live_app, "refreshburst")
    import http_sync
    entered, release, finished = Event(), Event(), Event()
    calls = []
    def slow_canvas():
        calls.append('refreshburst')
        entered.set()
        try:
            assert release.wait(5)
        finally:
            finished.set()
    monkeypatch.setattr(dashboard_app, "start_canvas_background_refresh",
                        lambda username: http_sync.submit_http_sync(username, 'canvas', slow_canvas))
    try:
        page.evaluate("""() => {
            window.slowPlatformsDone = false;
            Promise.all(Array.from({length: 6}, () => fetch('/api/canvas/todos?refresh=1').then(r => r.json())))
              .then(() => { window.slowPlatformsDone = true; });
        }""")
        assert entered.wait(timeout=5)
        page.wait_for_function('window.slowPlatformsDone === true', timeout=2000)
        assert calls == ['refreshburst']
        started = time.monotonic()
        assert page.request.get(f"{live_app}/api/clock", timeout=2000).ok
        assert page.request.get(f"{live_app}/api/actions", timeout=2000).ok
        assert time.monotonic() - started < 2
    finally:
        release.set()
        assert finished.wait(5)
    page.wait_for_function("window.slowPlatformsDone === true")


@pytest.mark.parametrize("reauth,count", [(False, 2), (True, 3)])
def test_refresh_waits_for_last_platform_then_shows_confirmed_failure_summary(live_app, browser, reauth, count):
    page = browser.new_page()
    page.goto(f"{live_app}/register")
    page.fill("#register-username", "summary")
    page.fill("#register-password", "strong-password")
    page.click("#register-form button")
    page.wait_for_url(f"{live_app}/")
    page.wait_for_function("Object.values(platformRequests).every(count => count === 0)")
    pending = []
    platforms = ["canvas", "haoke", "zhixuemeng"][:count]
    for platform in platforms:
        page.route(f"**/api/{platform}/todos*", lambda route: pending.append(route))
    page.click("#btn-refresh")
    page.wait_for_function("workspaceRefreshing === false")
    expect(page.locator("#btn-refresh")).to_have_attribute("aria-busy", "true")
    assert page.locator("#btn-refresh svg").evaluate("node => getComputedStyle(node).animationName") == "ui-control-spin"
    assert len(pending) == count
    failure = {"ok": False, "error": "确认失败", "data": [], "sync": {
        "connection_state": "needs_reauth" if reauth else "connected",
        "data_state": "cached", "error_code": "needs_reauth" if reauth else "sync_failed", "refreshing": False}}
    for route in pending[:-1]:
        route.fulfill(json=failure)
    expect(page.locator("#list-updated")).to_be_hidden()
    expect(page.locator("#btn-refresh")).to_have_attribute("aria-busy", "true")
    pending[-1].fulfill(json=failure)
    expect(page.locator("#list-updated")).to_have_text(f"{count} 处{'连接失败' if reauth else '未同步'}")
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true")
    assert page.locator("#btn-refresh svg").evaluate("node => getComputedStyle(node).animationName") == "none"
    # A successful retry removes the error summary without showing a success message.
    page.unroute_all()
    for platform in platforms:
        page.route(f"**/api/{platform}/todos*", lambda route: route.fulfill(json=_response()))
    page.click("#btn-refresh")
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true")
    expect(page.locator("#list-updated")).to_be_hidden()


def test_haoke_background_failure_stops_polling_without_restarting_stale_refresh(live_app, browser, monkeypatch):
    page = browser.new_page()
    username = "haokestatus"
    _open_connected_oj(page, live_app, username)
    tongji_oj_client.logout(username)
    haoke_client.save_credentials(username, "fake-student", "fake-password")
    platform_sync.mark_connected(username, "haoke")
    cache_file = haoke_client._cache_file(username)
    write_json_file(cache_file, [])
    os.utime(cache_file, (0, 0))
    started, release, finished = Event(), Event(), Event()
    calls = []
    original_worker = haoke_client._run_background_refresh
    def observed(username, identity, revision):
        try:
            original_worker(username, identity, revision)
        finally:
            finished.set()
    def slow_fetch(username, *, publish):
        assert publish is False
        calls.append(username)
        started.set()
        assert release.wait(10)
        return {"ok": False, "error": "confirmed upstream failure"}
    monkeypatch.setattr(haoke_client, "_run_background_refresh", observed)
    monkeypatch.setattr(haoke_client, "fetch_haoke_todos", slow_fetch)
    try:
        page.reload()
        assert started.wait(2)
        expect(page.locator("#btn-refresh")).to_have_attribute("aria-busy", "true")
        expect(page.locator("#list-updated")).to_be_hidden()
    finally:
        release.set()
        assert finished.wait(2)
    expect(page.locator("#list-updated")).to_have_text("1 处未同步", timeout=5000)
    expect(page.locator("#btn-refresh")).not_to_have_attribute("aria-busy", "true")
    assert calls == [username]

