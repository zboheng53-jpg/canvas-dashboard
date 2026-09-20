"""Verify focus actions and reversible project history in the real page."""
from datetime import timedelta
import pytest
from playwright.sync_api import expect
import app as dashboard
import project_store
import schedule_store
from test_visual_regression import register_dashboard_user


@pytest.mark.parametrize("width", [1440, 390])
def test_focus_select_today_complete_and_finished_group(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    try:
        username = register_dashboard_user(page, live_app, "focus")
        p = project_store.create_project(username, {"name": "探索项目"})
        today = dashboard.datetime.now(dashboard.CST).date()
        a = project_store.create_task(username, p["id"], {
            "name": "整理一个问题", "is_next_action": True,
            "commitment": "obligation", "planned_on": today.isoformat(),
            "due_date": (today + timedelta(days=7)).isoformat()
        })
        project_store.create_task(username, p["id"], {"name": "此前的计划", "planned_on": (today - timedelta(days=1)).isoformat()})
        project_store.create_task(username, p["id"], {"name": "未来的计划", "planned_on": (today + timedelta(days=1)).isoformat()})
        group = project_store.create_group(username, p["id"], "首次沟通")
        done = project_store.create_task(username, p["id"], {"name": "完成首次交流", "group_id": group["id"]})
        project_store.update_task(username, p["id"], done["id"], {"done": True})
        page.reload()
        todos = page.locator('#todo-list')
        expect(page.locator('.project-focus-card')).to_have_count(0)
        row = todos.locator('.todo-row').filter(has=page.get_by_role('button', name='整理一个问题', exact=True))
        expect(row).to_have_count(1)
        expect(todos.locator('.todo-group').filter(has=page.get_by_role('heading', name='今天', exact=True)).get_by_role('button', name='整理一个问题', exact=True)).to_be_visible()
        expect(todos.get_by_role('button', name='此前的计划', exact=True)).to_have_count(0)
        expect(todos.get_by_role('button', name='未来的计划', exact=True)).to_have_count(0)
        expect(page.locator('#src-count-project')).to_have_text('1')
        page.locator('[data-todo-source="custom"]').click()
        expect(row).to_have_count(0)
        page.locator('[data-todo-source="project"]').click()
        expect(row).to_have_count(1)
        if width < 768:
            row.get_by_role('button', name='更多操作', exact=True).click()
            actions = row.locator('.item-mobile-actions')
        else:
            actions = row.locator('.item-desktop-actions')
        actions.get_by_role('button', name='完成', exact=True).click()
        expect(row).to_have_count(0)
        assert next(t for t in project_store.load_projects(username)[0]['tasks'] if t['id'] == a['id'])['done']
        page.locator('#project-overview-content').get_by_role('button', name='探索项目', exact=True).click()
        history = page.locator('.project-finished-groups')
        expect(history).to_be_visible()
        assert history.get_attribute('open') is None
        expect(page.get_by_text('暂无未完成任务', exact=True)).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth') <= width
    finally:
        page.close()


def test_project_recycle_restore_and_materials(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        username = register_dashboard_user(page, live_app, 'recycle')
        p = project_store.create_project(username, {"name": "可恢复项目"})
        a = project_store.create_task(username, p['id'], {"name": "远期方向", "details": "保留原文"})
        page.reload()
        page.locator('#project-overview-content').get_by_role('button', name='可恢复项目', exact=True).click()
        # Ensure recycle bin tab does not exist
        expect(page.get_by_role('button', name='回收站', exact=True)).to_have_count(0)
        page.get_by_role('button', name='转为资料', exact=True).click()
        expect(page.locator('#project-detail').get_by_role('checkbox', name='完成远期方向', exact=True)).to_have_count(0)
        assert '保留原文' in project_store.load_projects(username)[0]['materials']
        expect(page.locator('.project-tab-btn[data-tab="active"]')).to_be_visible()
        expect(page.locator('#project-detail h2')).to_have_text('可恢复项目')
        page.locator('.project-more-menu summary').click()
        page.get_by_role('button', name='删除项目', exact=True).click()
        page.locator('#project-confirm-modal').get_by_role('button', name='永久删除', exact=True).click()
        expect(page.locator('#project-manager-list').get_by_role('button')).to_have_count(0)
        assert len(project_store.load_projects(username)) == 0
    finally:
        page.close()


def test_todo_delete_and_date_edit_for_project_task(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        username = register_dashboard_user(page, live_app, 'deletelinked')
        p = project_store.create_project(username, {"name": "同步项目"})
        day = dashboard.datetime.now(dashboard.CST).date().isoformat()
        a = project_store.create_task(username, p['id'], {"name": "今天的原任务", "planned_on": day})
        b = project_store.create_task(username, p['id'], {"name": "修改日期的任务", "planned_on": day})
        page.reload()
        row_a = page.locator('#todo-list .todo-row').filter(has=page.get_by_role('button', name='今天的原任务', exact=True))
        expect(row_a).to_be_visible()
        row_a.locator('.item-desktop-actions').get_by_role('button', name='删除', exact=True).click()
        page.locator('#project-confirm-modal').get_by_role('button', name='永久删除', exact=True).click()
        expect(row_a).to_have_count(0)
        tasks = project_store.load_projects(username)[0]['tasks']
        assert not any(t['id'] == a['id'] for t in tasks)

        row_b = page.locator('#todo-list .todo-row').filter(has=page.get_by_role('button', name='修改日期的任务', exact=True))
        expect(row_b).to_be_visible()
        row_b.get_by_role('button', name='修改计划日期', exact=True).click()
        date_input = row_b.locator('input[type="date"]')
        next_day = (dashboard.datetime.now(dashboard.CST).date() + timedelta(days=1)).isoformat()
        date_input.fill(next_day)
        date_input.press('Enter')
        expect(row_b).to_have_count(0)
        changed = next(t for t in project_store.load_projects(username)[0]['tasks'] if t['id'] == b['id'])
        assert changed['planned_on'] == next_day and changed['due_date'] is None
    finally:
        page.close()


def test_recurring_occurrence_completion_keeps_original_action(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        username = register_dashboard_user(page, live_app, 'repeatlinked')
        p = project_store.create_project(username, {"name": "重复项目"})
        a = project_store.create_task(username, p['id'], {"name": "一次练习"})
        day = dashboard.datetime.now(dashboard.CST).date()
        schedule_store.create_item(username, 'recurring', {
            'title': a['name'], 'action_ref': f"project:{p['id']}:{a['id']}",
            'weekday': day.weekday(), 'start_date': day.isoformat(),
            'end_date': (day + timedelta(days=7)).isoformat(), 'start_time': '19:00', 'end_time': '19:30'
        })
        page.reload()
        row = page.locator('#todo-list .todo-row').filter(has=page.get_by_role('button', name='一次练习', exact=True))
        expect(row).to_be_visible()
        expect(row).to_contain_text('19:00–19:30')
        page.locator('#today-schedule-content .forward-day').first.get_by_role('button', name='19:00–19:30 一次练习', exact=False).click()
        page.locator('#action-detail-dialog').get_by_role('button', name='完成本次安排', exact=True).click()
        page.get_by_role('button', name='关闭事项详情', exact=True).click()
        expect(row).to_have_count(0)
        assert not project_store.load_projects(username)[0]['tasks'][0]['done']
    finally:
        page.close()
