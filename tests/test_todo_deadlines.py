import re
from datetime import datetime, timedelta, timezone

import pytest

import auth
import recurring_todo_store
from action_contract import ActionValidationError
from platform_state import PlatformStateStore, build_platform_todos_response
from services import workspace
from storage import read_json_file, write_json_file

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 29, 12, tzinfo=CST)


@pytest.mark.parametrize("id_type", [str, int])
def test_completed_deadline_cleanup_is_permanent_and_preserves_pending(tmp_path, id_type):
    store = PlatformStateStore(lambda _: tmp_path / "state.json", id_type)
    ids = [id_type(i) for i in range(1, 7)]
    for item_id in ids[:4]:
        store.update("alice", "complete", item_id)
    store.update_override("alice", ids[3], {"due_ts": "2026-10-01"})
    items = [
        {"id": ids[0], "due_ts": "2026-09-23"},
        {"id": ids[1], "due_ts": "2026-09-29"},
        {"id": ids[2], "due_ts": None},
        {"id": ids[3], "due_ts": "2026-09-23"},
        {"id": ids[4], "due_ts": "2026-09-23"},
        {"id": ids[5], "due_ts": "2026-09-30"},
    ]
    original = [dict(item) for item in items]
    def project():
        return build_platform_todos_response({"data": items}, store.load("alice"), now=NOW,
            expire_completed=lambda entries, now: store.delete_expired_completed("alice", entries, now))
    response = project()
    assert [item["id"] for item in response["data"]] == ids[1:]
    assert response["deleted"] == [ids[0]]
    assert all(item["done"] for item in response["data"][:3])
    assert not response["data"][3].get("done")
    assert items == original  # Never rewrite upstream data.
    for action in ("undelete", "uncomplete"):
        store.update("alice", action, ids[0])
    store.update_override("alice", ids[0], {"due_ts": "2099-01-01"})
    assert [item["id"] for item in project()["data"]] == ids[1:]


def test_expiry_rechecks_latest_completion_and_override_inside_lock(tmp_path):
    store = PlatformStateStore(lambda _: tmp_path / "state.json", str)
    item = {"id": "one", "due_ts": "2026-09-23"}
    store.update("alice", "complete", "one")
    old = store.load("alice")
    store.update("alice", "uncomplete", "one")
    response = build_platform_todos_response({"data": [item]}, old, now=NOW,
        expire_completed=lambda items, now: store.delete_expired_completed("alice", items, now))
    assert len(response["data"]) == 1 and response["deleted"] == []


def test_custom_completed_cleanup_uses_deadline_not_completion_time(isolated_data):
    auth.register("alice", "password1")
    path = isolated_data / "users/alice/custom_todos.json"
    write_json_file(path, [
        {"id": 1, "text": "完成且过期", "done": True, "due_date": "2026-09-23", "completed_at": NOW.isoformat(), "request_id": "old"},
        {"id": 2, "text": "完成但未截止", "done": True, "due_date": "2026-09-30"},
        {"id": 3, "text": "完成且无截止", "done": True, "due_date": None},
        {"id": 4, "text": "未完成且逾期", "done": False, "due_date": "2026-09-23"},
    ])
    todos = workspace._remove_expired_completed_todos("alice", NOW.date())
    assert [t["id"] for t in todos] == [2, 3, 4]
    assert [t["id"] for t in read_json_file(path, [])] == [2, 3, 4]


def test_recurring_expiry_deletes_only_completed_occurrence(isolated_data):
    auth.register("alice", "password1")
    series = recurring_todo_store.create_series("alice", {"title": "每周作业", "first_due_date": "2026-09-23", "interval_weeks": 1})
    recurring_todo_store.complete_occurrence("alice", series["id"], "2026-09-23", True)
    items = recurring_todo_store.get_homepage_items("alice", today=NOW.date())
    assert len(items) == 1 and items[0]["due_date"] == "2026-09-30"
    with pytest.raises(ActionValidationError, match="永久删除"):
        recurring_todo_store.complete_occurrence("alice", series["id"], "2026-09-23", False)
    assert recurring_todo_store.get_occurrence_by_ref("alice", "recurring:1:2026-09-23") is None
    assert recurring_todo_store.get_series("alice", 1) is not None


def test_dashboard_four_deadline_states(live_app, isolated_data, browser, test_now):
    # Actual renderer, server cleanup, and computed colors; no production data.
    # Offsets stay inside the 3-day yellow window so the case does not depend on
    # where the rolling 7-day "本周内" boundary falls on the real clock.
    auth.register("deadlineuser", "strong-password")
    day = lambda offset: (test_now.date() + timedelta(days=offset)).isoformat()
    write_json_file(isolated_data / "users/deadlineuser/custom_todos.json", [
        {"id": 1, "text": "完成过期应删除", "done": True, "due_date": day(-1), "request_id": "fixture-old"},
        {"id": 2, "text": "完成未截止应沉底", "done": True, "due_date": day(3)},
        {"id": 3, "text": "未完成逾期应标红", "done": False, "due_date": day(-1)},
        {"id": 4, "text": "未完成三天内应标黄", "done": False, "due_date": day(2)},
        {"id": 5, "text": "未完成今日应标红", "done": False, "due_date": day(0)},
        {"id": 6, "text": "未完成无日期沉底", "done": False, "due_date": None},
    ])
    page = browser.new_page()
    page.goto(live_app + "/login")
    page.fill("#login-username", "deadlineuser")
    page.fill("#login-password", "strong-password")
    page.click("#login-form button")
    page.wait_for_url(live_app + "/")
    from playwright.sync_api import expect
    expect(page.locator('.todo-row').filter(has_text="未完成逾期应标红")).to_be_visible()
    assert "完成过期应删除" not in page.locator("#todo-list").inner_text()
    completed = page.locator('[data-group-key="completed"]')
    expect(completed).to_have_count(1)
    if completed.locator('.todo-group-heading').get_attribute('aria-expanded') == 'false':
        completed.locator('.todo-group-heading').click()
    expect(completed).to_contain_text("完成未截止应沉底")
    # 固定分组层次：已逾期 → 今天 → 无日期，且不再有「明天」「此前未完成」。
    keys = page.locator(".todo-group").evaluate_all("nodes => nodes.map(n => n.dataset.groupKey)")
    assert "tomorrow" not in keys and "previous" not in keys
    assert keys == [k for k in ["overdue", "today", "week", "nodate", "later", "completed"] if k in keys]
    assert keys.index("overdue") < keys.index("today")
    assert keys.index("today") < keys.index("nodate")
    assert "completed" not in keys or keys[-1] == "completed"
    # 视觉语言：截止标签始终是同一枚胶囊（圆角 999px + 淡底色），只换字色与底色深浅——
    # 逾期＝红字粉底且整行红底，今天＝红字粉底但整行白底，三天内＝黄字黄底，无日期＝灰蓝字浅灰底。
    expected = {
        "未完成逾期应标红": ("rgb(214, 69, 69)", "rgb(253, 240, 240)"),
        "未完成今日应标红": ("rgb(214, 69, 69)", "rgb(253, 240, 240)"),
        "未完成三天内应标黄": ("rgb(176, 114, 8)", "rgb(253, 246, 231)"),
        "未完成无日期沉底": ("rgb(91, 100, 114)", "rgb(243, 246, 249)"),
    }
    for title, (color, background) in expected.items():
        row = page.locator('.todo-row').filter(has_text=title)
        due = row.locator('.item-due')
        expect(due).to_have_css("color", color)
        expect(due).to_have_css("background-color", background)
        expect(due).to_have_css("border-radius", "999px")
    # 行底色只区分逾期与今天：逾期整行红底，今天与三天内都不铺底色。
    overdue_row = page.locator('.todo-row').filter(has_text="未完成逾期应标红")
    expect(overdue_row).to_have_class(re.compile(r"\bui-list-item--danger\b"))
    expect(overdue_row).to_have_css("background-color", "rgb(253, 240, 240)")
    for title in ["未完成今日应标红", "未完成三天内应标黄"]:
        plain_row = page.locator('.todo-row').filter(has_text=title)
        expect(plain_row).not_to_have_class(re.compile(r"\bui-list-item--(danger|warning)\b"))
        expect(plain_row).to_have_css("background-color", "rgba(0, 0, 0, 0)")
    assert [t["id"] for t in read_json_file(isolated_data / "users/deadlineuser/custom_todos.json", [])] == [2, 3, 4, 5, 6]
    page.close()
