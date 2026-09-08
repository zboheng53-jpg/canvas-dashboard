"""Dense desktop weeks must keep every time band visible and every item reachable."""
from datetime import datetime

import pytest
from playwright.sync_api import expect

import app as dashboard
import project_store
import schedule_store
from test_visual_regression import register_dashboard_user


@pytest.mark.parametrize("width,height", [(1536, 832), (1280, 720)])
def test_dense_week_fits_and_overflow_opens_same_action(live_app, browser, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        username = register_dashboard_user(page, live_app, "dense")
        day = datetime.now(dashboard.CST).date().isoformat()
        project = project_store.create_project(username, {"name": "英语练习"})
        for i in range(12):
            project_store.create_task(username, project["id"], {
                "name": f"听力练习与错题复盘 {i + 1}", "planned_on": day,
                "details": "完整的执行说明保持可读，不挤在列表中。",
            })
        schedule_store.create_item(username, "one_off", {
            "title": "晚间复盘", "date": day, "start_time": "19:00", "end_time": "19:30",
        })
        page.reload()
        page.get_by_role("button", name="日程与课表", exact=True).click()
        page.wait_for_selector(".period-cell")
        evening = page.locator(f'.period-cell[data-date="{day}"][data-period="eve"]')
        expect(evening.get_by_role("button", name="19:00–19:30 晚间复盘", exact=True)).to_be_visible()
        rects = page.locator(f'.period-cell[data-date="{day}"]').evaluate_all(
            "nodes => nodes.map(e => { const r=e.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,height:r.height}; })"
        )
        assert len(rects) == 4
        assert all(0 <= r["top"] < r["bottom"] <= height for r in rects)
        assert max(r["height"] for r in rects) - min(r["height"] for r in rects) < 1
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        grid = page.locator("#schedule-timetable-grid")
        assert "成长" not in grid.inner_text() and "责任" not in grid.inner_text()
        cell = page.locator(f'.period-cell[data-date="{day}"][data-period="all"]')
        more = cell.locator(".period-more")
        expect(more).to_be_visible()
        assert cell.locator(".period-event:visible").count() >= 1
        more.click()
        dialog = page.locator("#period-entries-dialog")
        expect(dialog.locator(".period-event")).to_have_count(12)
        dialog.get_by_role("button", name="计划推进 · 未定时间 听力练习与错题复盘 12", exact=True).click()
        detail = page.locator("#action-detail-dialog")
        expect(detail).to_be_visible()
        expect(dialog).not_to_be_visible()
        expect(detail).to_contain_text("完整的执行说明保持可读")
        detail.get_by_role("button", name="编辑事项", exact=True).click()
        detail.get_by_role("checkbox", name="同时加入待办清单", exact=True).check()
        detail.get_by_role("button", name="保存事项", exact=True).click()
        expect(detail.get_by_role("button", name="编辑事项", exact=True)).to_be_visible()
        assert len(project_store.todo_items(username)) == 1
    finally:
        page.close()
