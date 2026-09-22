import re
import uuid
import pytest
from playwright.sync_api import expect


def register_user(page, live_app, prefix="ux"):
    uid = uuid.uuid4().hex[:6]
    username = f"{prefix}_{uid}"
    page.goto(f"{live_app}/register")
    page.fill("#register-username", username)
    page.fill("#register-password", "password123")
    page.click("#register-form button")
    page.wait_for_selector(".dashboard-shell")
    return username


@pytest.mark.parametrize("width", [360, 390, 430])
def test_mobile_todo_input_geometry_and_wrapping(live_app, browser, width):
    """UI-02: Validate mobile add-todo input takes full line and controls wrap below."""
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_user(page, live_app, f"m{width}")

    input_loc = page.locator("#new-todo-input")
    due_loc = page.locator("#new-todo-due")
    btn_loc = page.locator("#btn-add-todo")

    expect(input_loc).to_be_visible()
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
    """UI-03: Verify deletion confirmation dialog, cancel, and confirmed delete."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "del_flow")

    # Add a custom todo
    page.fill("#new-todo-input", "待确认删除任务")
    page.click("#btn-add-todo")
    todo_row = page.locator(".todo-row", has_text="待确认删除任务")
    expect(todo_row).to_be_visible()

    del_btn = todo_row.locator(".item-desktop-actions .btn-delete")

    # 1. Dismiss confirmation: dialog canceled
    page.once("dialog", lambda dialog: dialog.dismiss())
    del_btn.click()

    # Should still exist
    expect(todo_row).to_be_visible()

    # 2. Accept confirmation: dialog confirmed
    page.once("dialog", lambda dialog: dialog.accept())
    del_btn.click()

    # Should be removed
    expect(page.locator(".todo-row", has_text="待确认删除任务")).not_to_be_visible()
    page.close()


def test_collapsible_groups_and_counts(live_app, browser):
    """UI-05: Verify collapsible todo groups and group count badges."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "grp_collapse")

    # Add items
    page.fill("#new-todo-input", "今天待办测试")
    page.click("#btn-add-todo")
    expect(page.locator(".todo-row", has_text="今天待办测试")).to_be_visible()

    # Test collapsible group
    today_group_head = page.locator('.todo-group[data-group-key="today"] .todo-group-heading')
    expect(today_group_head).to_be_visible()
    expect(today_group_head.locator('.ui-count-pill')).to_have_text("1")

    # Click to collapse
    today_group_head.click()
    today_items = page.locator('.todo-group[data-group-key="today"] .todo-group-items')
    expect(today_items).not_to_be_visible()

    # Click to expand
    today_group_head.click()
    expect(today_items).to_be_visible()
    page.close()


def test_search_action_dialog_entry_and_focus(live_app, browser):
    """UI-06: Verify search buttons in overview and schedule, and focus return."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    register_user(page, live_app, "srch_focus")

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
