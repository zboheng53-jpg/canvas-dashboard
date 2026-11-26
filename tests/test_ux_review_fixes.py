import re
import uuid
import pytest
from playwright.sync_api import expect

import browser_env


def register_user(page, live_app, prefix="ux"):
    uid = uuid.uuid4().hex[:6]
    username = f"{prefix}_{uid}"
    page.goto(f"{live_app}/register")
    page.fill("#register-username", username)
    page.fill("#register-password", "password123")
    page.click("#register-form button")
    page.wait_for_selector(".dashboard-shell")
    browser_env.wait_for_layout_settled(page)
    return username


@pytest.mark.parametrize("width", [360, 390, 430])
def test_mobile_todo_input_geometry_and_wrapping(live_app, browser, width):
    """UI-02: Validate mobile add-todo input takes full line and controls wrap below."""
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_user(page, live_app, f"m{width}")
    page.locator("#mobile-add-toggle").click()

    input_loc = page.locator("#new-todo-input")
    due_loc = page.locator("#new-todo-due")
    btn_loc = page.locator("#btn-add-todo")

    expect(input_loc).to_be_visible()
    # 展开输入区会改变容器高度，等布局稳定后再测量换行关系。
    browser_env.wait_for_layout_settled(page)
    input_box = input_loc.bounding_box()
    due_box = due_loc.bounding_box()
    btn_box = btn_loc.bounding_box()

    assert input_box is not None
    assert due_box is not None
    assert btn_box is not None

    # Title input must be spacious (at least 240px wide on 360px+ screen)
    assert input_box["width"] >= 240, f"Title input was squished to {input_box['width']}px"

    # Date and button must wrap onto subsequent line (their y position > title input y)
    assert due_box["y"] >= input_box["y"] + input_box["height"] - 4, "Date input did not wrap to second line"
    assert btn_box["y"] >= input_box["y"] + input_box["height"] - 4, "Button did not wrap to second line"

    # Verify actual interaction: type and submit
    page.fill("#new-todo-input", f"移动端响应式测试任务-{width}")
    btn_loc.click()

    # The new todo should appear in the list
    expect(page.locator(".todo-row", has_text=f"移动端响应式测试任务-{width}")).to_be_visible()
    page.close()


def test_custom_todo_delete_confirmation_flow(live_app, browser):
    """UI-03: Verify custom #ui-confirm-dialog cancel and confirmed delete without native dialogs."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    native_dialogs = []
    page.on("dialog", lambda dialog: (native_dialogs.append(dialog.message), dialog.dismiss()))
    register_user(page, live_app, "del_flow")

    # Add a custom todo
    page.fill("#new-todo-input", "待确认删除任务")
    page.click("#btn-add-todo")
    todo_row = page.locator(".todo-row", has_text="待确认删除任务")
    expect(todo_row).to_be_visible()

    del_btn = todo_row.locator(".item-desktop-actions .btn-delete")
    confirm_dialog = page.locator("#ui-confirm-dialog")

    # 1. Dismiss confirmation: dialog canceled
    del_btn.click()
    expect(confirm_dialog).to_be_visible()
    expect(confirm_dialog).to_contain_text("待确认删除任务")
    cancel_btn = confirm_dialog.locator(".ui-button--secondary[data-ui-confirm-cancel]")
    expect(cancel_btn).to_have_text("取消")
    cancel_btn.click()
    expect(confirm_dialog).not_to_be_visible()

    # Should still exist
    expect(todo_row).to_be_visible()

    # 2. Accept confirmation: dialog confirmed
    del_btn.click()
    expect(confirm_dialog).to_be_visible()
    accept_btn = confirm_dialog.locator("[data-ui-confirm-accept]")
    expect(accept_btn).to_have_text("永久删除")
    accept_btn.click()
    expect(confirm_dialog).not_to_be_visible()

    # Should be removed
    expect(page.locator(".todo-row", has_text="待确认删除任务")).not_to_be_visible()
    assert native_dialogs == []
    page.close()


def test_collapsible_groups_and_counts(live_app, browser, test_now):
    """UI-05: Verify in-place collapsible todo groups, aria-expanded, and group count badges."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "grp_collapse")

    # Add items
    page.fill("#new-todo-input", "今天待办测试")
    page.fill("#new-todo-due", test_now.date().isoformat())
    page.click("#btn-add-todo")
    today_row = page.locator(".todo-row", has_text="今天待办测试")
    expect(today_row).to_be_visible()

    # Test collapsible group
    today_group_head = page.locator('.todo-group[data-group-key="today"] .todo-group-heading')
    expect(today_group_head).to_be_visible()
    expect(today_group_head).to_have_attribute("aria-expanded", "true")
    expect(today_group_head.locator('.ui-count-pill')).to_have_text("1")

    # Row node remains mounted in place (no full list DOM wipe)
    row_handle = page.evaluate_handle("document.querySelector('.todo-group[data-group-key=\"today\"] .todo-row')")

    # Click to collapse
    today_group_head.click()
    today_items = page.locator('.todo-group[data-group-key="today"] .todo-group-items')
    expect(today_group_head).to_have_attribute("aria-expanded", "false")
    expect(today_items).not_to_be_visible()

    # Click to expand
    today_group_head.click()
    expect(today_group_head).to_have_attribute("aria-expanded", "true")
    expect(today_items).to_be_visible()
    assert page.evaluate("el => el.isConnected", row_handle) is True
    page.close()


def test_search_action_dialog_entry_and_focus(live_app, browser):
    """UI-06: Verify search buttons, Ctrl/Cmd+K shortcut, keyboard navigation, and focus return."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "srch_focus")

    # Add searchable custom todo
    page.fill("#new-todo-input", "快捷键搜索目标")
    page.click("#btn-add-todo")
    expect(page.locator(".todo-row", has_text="快捷键搜索目标")).to_be_visible()

    # 1. Search button in today schedule card
    search_btn = page.locator("#btn-search-actions")
    expect(search_btn).to_be_visible()

    search_btn.click()
    dialog = page.locator("#action-search-dialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#action-search-title")).to_have_text("查找事项")

    # Press Escape to close
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()

    # Verify focus returned to search button
    expect(search_btn).to_be_focused()

    # 2. Search button in weekly schedule
    page.click('[data-dashboard-view="schedule"]')
    expect(page.locator("#dashboard-view-schedule")).to_be_visible()

    schedule_search_btn = page.locator("#schedule-header-search-btn")
    expect(schedule_search_btn).to_be_visible()
    schedule_search_btn.click()
    expect(dialog).to_be_visible()

    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(schedule_search_btn).to_be_focused()

    # 3. Global Ctrl+K shortcut and ArrowDown + Enter navigation
    page.keyboard.press("Control+k")
    expect(dialog).to_be_visible()
    search_input = page.locator("#action-search-input")
    expect(search_input).to_be_focused()
    search_input.fill("快捷键搜索目标")
    result_item = page.locator("#action-search-list .action-pool-item", has_text="快捷键搜索目标")
    expect(result_item).to_be_visible()
    expect(result_item).to_have_class(re.compile(r"\bis-active\b"))
    search_input.press("ArrowDown")
    search_input.press("Enter")
    detail_dialog = page.locator("#action-detail-dialog")
    expect(detail_dialog).to_be_visible()
    expect(page.locator("#action-detail-title")).to_have_text("快捷键搜索目标")
    page.keyboard.press("Escape")
    expect(detail_dialog).not_to_be_visible()
    page.close()


def test_custom_todo_title_click_inline_edit(live_app, browser):
    """Verify custom todo title click enters inline edit directly (original design)."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "inline_edit")

    # Add custom todo
    page.fill("#new-todo-input", "点击标题直接行内编辑待办")
    page.click("#btn-add-todo")
    todo_row = page.locator(".todo-row", has_text="点击标题直接行内编辑待办")
    expect(todo_row).to_be_visible()

    title_el = todo_row.locator(".editable-title")
    expect(title_el).to_be_visible()

    # Clicking title opens inline edit directly
    title_el.click()
    inline_input = page.locator(".inline-edit-input")
    expect(inline_input).to_be_visible()
    inline_input.fill("修改完成后的行内待办")
    page.keyboard.press("Enter")

    # Verify updated
    expect(page.locator(".todo-row", has_text="修改完成后的行内待办")).to_be_visible()
    page.close()


def test_add_todo_protection_and_error_handling(live_app, browser):
    """UI-08: Verify submit button loading state and error handling without losing input."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "add_prot")

    input_loc = page.locator("#new-todo-input")
    btn_loc = page.locator("#btn-add-todo")

    # Normal submission
    input_loc.fill("普通保护测试")
    btn_loc.click()
    expect(page.locator(".todo-row", has_text="普通保护测试")).to_be_visible()
    # Input is cleared on success
    expect(input_loc).to_have_value("")

    # Verify error display does not wipe input when API fails
    # Simulate API failure via route abort/fulfill with error
    page.route("**/api/custom/todos", lambda route: route.fulfill(
        status=500,
        content_type="application/json",
        body='{"error": "测试服务端故障"}'
    ))

    input_loc.fill("失败保留文本测试")
    btn_loc.click()

    error_el = page.locator("#add-todo-error")
    expect(error_el).to_be_visible()
    expect(error_el).to_contain_text("测试服务端故障")

    # Input value must NOT be cleared on failure!
    expect(input_loc).to_have_value("失败保留文本测试")
    expect(btn_loc).to_be_enabled()
    page.close()


def test_subtask_edit_guard_and_completion_undo_toast(live_app, browser):
    """Verify subtask edit guard against double-PUT/re-render and Undo toast on completion."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "sub_undo")

    page.fill("#new-todo-input", "子任务与撤销测试")
    page.click("#btn-add-todo")
    wrap = page.locator(".todo-row-wrap", has_text="子任务与撤销测试")
    expect(wrap).to_be_visible()

    # Desktop detail button opens #action-detail-dialog
    wrap.locator(".item-desktop-actions .btn-detail").click()
    detail_dialog = page.locator("#action-detail-dialog")
    expect(detail_dialog).to_be_visible()
    expect(page.locator("#action-detail-title")).to_have_text("子任务与撤销测试")
    page.keyboard.press("Escape")
    expect(detail_dialog).not_to_be_visible()

    # Expand subtasks and add one
    wrap.locator(".subtask-toggle").click()
    wrap.locator(".subtask-add-input").fill("初始子步骤")
    wrap.locator(".subtask-add-input").press("Enter")
    sub_text = wrap.locator(".subtask-text", has_text="初始子步骤")
    expect(sub_text).to_be_visible()

    # Edit subtask and confirm renderUnifiedList() skips active .subtask-edit-input + only 1 PUT fires
    put_count = 0

    def count_puts(route):
        nonlocal put_count
        if route.request.method == "PUT":
            put_count += 1
        route.continue_()

    page.route("**/api/custom/todos/*", count_puts)
    sub_text.click()
    edit_input = wrap.locator(".subtask-edit-input")
    expect(edit_input).to_be_visible()
    edit_input.fill("已改名子步骤")
    page.evaluate("renderUnifiedList()")
    expect(edit_input).to_be_focused()
    expect(edit_input).to_have_value("已改名子步骤")
    with page.expect_response(lambda r: "/api/custom/todos/" in r.url and r.request.method == "PUT"):
        edit_input.press("Enter")
    page.wait_for_timeout(100)
    assert put_count == 1
    expect(wrap.locator(".subtask-text", has_text="已改名子步骤")).to_be_visible()
    page.unroute("**/api/custom/todos/*")

    # Complete todo: completed group stays collapsed and Undo toast restores it
    wrap.locator(".item-desktop-actions .btn-dismiss").click()
    completed_group = page.locator('.todo-group[data-group-key="completed"]')
    expect(completed_group).to_be_visible()
    expect(completed_group.locator(".todo-group-heading")).to_have_attribute("aria-expanded", "false")
    toast_region = page.locator("#ui-toast-region")
    expect(toast_region).to_contain_text("已完成")
    toast_region.get_by_role("button", name="撤销").click()
    expect(page.locator('.todo-group[data-group-key="nodate"] .todo-row', has_text="子任务与撤销测试")).to_be_visible()
    page.close()
