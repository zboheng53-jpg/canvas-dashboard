"""Verify focus actions and reversible project history in the real page."""
import pytest
from playwright.sync_api import expect
import app as dashboard
import project_store
from test_visual_regression import register_dashboard_user


@pytest.mark.parametrize("width", [1440, 390])
def test_focus_select_today_complete_and_finished_group(live_app, browser, width):
    page = browser.new_page(viewport={"width":width,"height":900})
    try:
        username = register_dashboard_user(page, live_app, "focus")
        p = project_store.create_project(username, {"name":"探索项目"})
        a = project_store.create_task(username,p["id"],{"name":"整理一个问题","is_next_action":True})
        group = project_store.create_group(username,p["id"],"首次沟通")
        done = project_store.create_task(username,p["id"],{"name":"完成首次交流","group_id":group["id"]})
        project_store.update_task(username,p["id"],done["id"],{"done":True})
        page.reload()
        focus = page.locator('#project-focus-content')
        expect(focus.get_by_text('可选下一步 · 尚未排入今天 · 1', exact=True)).to_be_visible()
        focus.get_by_role('button',name='今天做',exact=True).click()
        expect(focus.locator('.project-focus-today').get_by_role('button',name='整理一个问题',exact=True)).to_be_visible()
        today = dashboard.datetime.now(dashboard.CST).date().isoformat()
        assert next(t for t in project_store.load_projects(username)[0]['tasks'] if t['id']==a['id'])['planned_on'] == today
        focus.get_by_role('button',name='完成行动',exact=True).click()
        expect(focus.get_by_role('button',name='整理一个问题',exact=True)).to_have_count(0)
        page.locator('#project-overview-content').get_by_role('button',name='探索项目',exact=True).click()
        history = page.locator('.project-finished-groups')
        expect(history).to_be_visible()
        assert history.get_attribute('open') is None
        expect(page.get_by_text('暂无未完成任务',exact=True)).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth') <= width
    finally:
        page.close()


def test_project_recycle_restore_and_materials(live_app, browser):
    page=browser.new_page(viewport={"width":1440,"height":900})
    try:
        username=register_dashboard_user(page,live_app,'recycle')
        p=project_store.create_project(username,{"name":"可恢复项目"})
        a=project_store.create_task(username,p['id'],{"name":"远期方向","details":"保留原文"})
        page.reload()
        page.locator('#project-overview-content').get_by_role('button',name='可恢复项目',exact=True).click()
        page.get_by_role('button',name='转为资料',exact=True).click()
        expect(page.locator('#project-detail').get_by_role('checkbox',name='完成远期方向',exact=True)).to_have_count(0)
        assert '保留原文' in project_store.load_projects(username)[0]['materials']
        page.get_by_role('button',name='回收站',exact=True).click()
        page.get_by_role('button',name='恢复任务',exact=True).click()
        expect(page.get_by_text('回收站为空。',exact=True)).to_be_visible()
        page.locator('.project-tab-btn[data-tab="active"]').click()
        expect(page.locator('#project-detail h2')).to_have_text('可恢复项目')
        page.locator('.project-more-menu summary').click()
        page.get_by_role('button',name='删除项目',exact=True).click()
        page.locator('#project-confirm-modal').get_by_role('button',name='移入回收站',exact=True).click()
        expect(page.locator('#project-manager-list').get_by_role('button')).to_have_count(0)
        page.get_by_role('button',name='回收站',exact=True).click()
        page.get_by_role('button',name='恢复项目',exact=True).click()
        expect(page.get_by_text('回收站为空。',exact=True)).to_be_visible()
        restored=project_store.load_projects(username)[0]
        assert restored['id']==p['id'] and restored['tasks'][0]['id']==a['id']
    finally:
        page.close()
