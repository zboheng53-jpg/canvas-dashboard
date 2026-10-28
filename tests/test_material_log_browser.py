"""Material-page flows use the production API and isolated synthetic projects."""
import pytest
from playwright.sync_api import expect

import project_store
from test_visual_regression import register_dashboard_user


def open_materials(page, project_id=None):
    if project_id is None:
        page.evaluate("switchDashboardView('materials')")
    else:
        page.evaluate("id => openProjectMaterials(id)", project_id)
    expect(page.locator('#materials-container')).to_have_attribute('aria-busy', 'false')


def project(username, name='研究记录', materials=''):
    return project_store.create_project(username, {'name': name, 'materials': materials})


@pytest.mark.parametrize('width', [1440, 390])
def test_material_filter_history_and_single_navigation_request(live_app, browser, width):
    page = browser.new_page(viewport={'width': width, 'height': 900})
    try:
        username = register_dashboard_user(page, live_app, 'matfilter')
        first = project(username, materials='【2026-07-09 记录】\n最新正文\n【2026-07-08 记录】\n历史正文')
        second = project(username, '第二项目', '没有日期的背景正文')
        requests = []
        page.on('request', lambda request: requests.append(request.url) if '/api/materials' in request.url else None)
        open_materials(page, first['id'])
        assert len(requests) == 1 and requests[0].endswith('/api/materials')
        expect(page.locator('#materials-project-filter option')).to_have_count(3)
        expect(page.locator('.materials-latest-section')).to_contain_text('最新正文')
        expect(page.locator('#materials-history')).not_to_have_attribute('open', '')
        expect(page.get_by_text('历史正文', exact=False)).not_to_be_visible()
        page.locator('#materials-project-filter').select_option(str(second['id']))
        expect(page.locator('#materials-project-filter option')).to_have_count(3)
        expect(page.locator('.materials-latest-section')).to_have_count(0)
        expect(page.locator('#materials-history')).not_to_have_attribute('open', '')
        expect(page.get_by_text('没有日期的背景正文', exact=True)).not_to_be_visible()
        page.locator('#materials-history summary').click()
        expect(page.get_by_text('没有日期的背景正文', exact=True)).to_be_visible()
        page.locator('#materials-project-filter').select_option('')
        expect(page.locator('.material-entry-card')).to_have_count(3)
        assert len(requests) == 1
        assert page.evaluate('document.documentElement.scrollWidth') <= width
    finally:
        page.close()


def test_material_create_edit_delete_dirty_focus_and_today(live_app, browser, test_now):
    page = browser.new_page()
    try:
        username = register_dashboard_user(page, live_app, 'matcrud')
        p = project(username)
        open_materials(page, p['id'])
        new_button = page.locator('#materials-new-button')
        new_button.click()
        expect(page.locator('#material-form-body')).to_be_focused()
        expect(page.locator('#material-form-date')).to_have_value(test_now.date().isoformat())
        page.locator('#material-form-body').fill('尚未保存')
        page.keyboard.press('Escape')
        expect(page.locator('#material-entry-modal')).to_be_visible()
        expect(page.locator('#material-entry-error')).to_contain_text('未保存')
        page.locator('#material-entry-modal').get_by_role('button', name='取消', exact=True).click()
        expect(new_button).to_be_focused()
        new_button.click()
        body = '  新日志\n保留尾部  '
        page.locator('#material-form-body').fill(body)
        page.locator('#material-entry-save-btn').click()
        expect(page.locator('#material-entry-modal')).not_to_be_visible()
        expect(page.locator('.material-entry-card')).to_have_count(1)
        entry = project_store.material_log(username)['entries'][0]
        assert entry['body'] == body and entry['date'] == test_now.date().isoformat()
        page.locator('[data-material-action="edit"]').click()
        expect(page.locator('#material-form-project')).to_be_disabled()
        page.locator('#material-form-body').fill('更新的记录')
        page.locator('#material-entry-save-btn').click()
        expect(page.locator('.material-entry-body')).to_have_text('更新的记录')
        page.once('dialog', lambda dialog: dialog.dismiss())
        page.locator('[data-material-action="delete"]').click()
        expect(page.locator('.material-entry-card')).to_have_count(1)
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('[data-material-action="delete"]').click()
        expect(page.locator('.material-entry-card')).to_have_count(0)
        assert project_store.material_log(username)['entries'] == []
    finally:
        page.close()


def test_material_retry_uses_same_id_after_real_server_commit(live_app, browser):
    page = browser.new_page()
    try:
        username = register_dashboard_user(page, live_app, 'matretry')
        p = project(username)
        open_materials(page, p['id'])
        attempts = []
        def lose_first_response(route):
            attempts.append(route.request.post_data_json['request_id'])
            if len(attempts) == 1:
                response = route.fetch()
                assert response.ok
                route.abort()
            else:
                route.continue_()
        page.route(f'**/api/projects/{p["id"]}/materials', lose_first_response)
        page.locator('#materials-new-button').click()
        page.locator('#material-form-body').fill('网络中断后重试')
        page.locator('#material-entry-save-btn').click()
        expect(page.locator('#material-entry-error')).not_to_be_empty()
        expect(page.locator('#material-form-body')).to_have_value('网络中断后重试')
        assert len(project_store.material_log(username)['entries']) == 1
        page.locator('#material-entry-save-btn').click()
        expect(page.locator('#material-entry-modal')).not_to_be_visible()
        assert len(attempts) == 2 and attempts[0] == attempts[1]
        assert len(project_store.material_log(username)['entries']) == 1
    finally:
        page.close()


def test_material_conflicts_preserve_inputs_and_failed_delete_stays_open(live_app, browser):
    page = browser.new_page()
    try:
        username = register_dashboard_user(page, live_app, 'matconflict')
        p = project(username)
        entry = project_store.create_material_entry(username, p['id'], {'body': '原记录', 'date': '2026-07-09'})
        open_materials(page, p['id'])
        page.locator('[data-material-action="edit"]').click()
        page.locator('#material-form-body').fill('我的修改')
        project_store.update_material_entry(username, p['id'], entry['id'], {'body': '另一端修改', 'expected_updated_at': entry['updated_at']})
        page.locator('#material-entry-save-btn').click()
        expect(page.locator('#material-entry-error')).to_contain_text('已被修改')
        expect(page.locator('#material-form-body')).to_have_value('我的修改')
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#material-entry-delete-btn').click()
        expect(page.locator('#material-entry-error')).to_contain_text('已被修改')
        expect(page.locator('#material-entry-modal')).to_be_visible()
        assert project_store.material_log(username)['entries'][0]['body'] == '另一端修改'
        page.locator('#material-entry-modal').get_by_role('button', name='取消', exact=True).click()
    finally:
        page.close()


def test_legacy_raw_preservation_edit_and_conflict(live_app, browser):
    page = browser.new_page()
    try:
        username = register_dashboard_user(page, live_app, 'matraw')
        raw = '  前言\r\n【2026-07-09 记录】\r\n正文\n尾部  \r\n'
        p = project(username, materials=raw)
        open_materials(page, p['id'])
        page.locator('.materials-latest-section [data-material-action="legacy"]').click()
        page.locator('#legacy-materials-save-btn').click()
        expect(page.locator('#legacy-materials-modal')).not_to_be_visible()
        assert project_store.load_projects(username)[0]['materials'] == raw
        expect(page.locator('#materials-container')).to_have_attribute('aria-busy', 'false')
        page.locator('.materials-latest-section [data-material-action="legacy"]').click()
        changed = '  【2026-07-09 新原文】\n修改正文  \n'
        page.locator('#legacy-materials-body').fill(changed)
        page.locator('#legacy-materials-save-btn').click()
        expect(page.locator('#legacy-materials-modal')).not_to_be_visible()
        assert project_store.load_projects(username)[0]['materials'] == changed
        expect(page.locator('#materials-container')).to_have_attribute('aria-busy', 'false')
        page.locator('.materials-latest-section [data-material-action="legacy"]').click()
        page.locator('#legacy-materials-body').fill('保留我的未保存文本  ')
        project_store.update_project(username, p['id'], {'objective': '并发改动'})
        page.locator('#legacy-materials-save-btn').click()
        expect(page.locator('#legacy-materials-error')).to_contain_text('已被修改')
        expect(page.locator('#legacy-materials-body')).to_have_value('保留我的未保存文本  ')
        page.locator('#legacy-materials-modal').get_by_role('button', name='取消', exact=True).click()
    finally:
        page.close()


def test_material_load_failure_is_visible_and_retry_uses_real_api(live_app, browser):
    page = browser.new_page()
    try:
        username = register_dashboard_user(page, live_app, 'matload')
        p = project(username, materials='【2026-07-09 记录】\n真实接口返回的内容')
        page.route('**/api/materials', lambda route: route.fulfill(status=503, json={'ok': False, 'error': '服务暂不可用'}))
        open_materials(page, p['id'])
        expect(page.locator('#materials-status')).to_contain_text('加载资料失败')
        expect(page.locator('.material-entry-card')).to_have_count(0)
        expect(page.locator('#materials-new-button')).to_be_disabled()
        page.unroute('**/api/materials')
        page.locator('[data-material-action="retry"]').click()
        expect(page.locator('.material-entry-body')).to_contain_text('真实接口返回的内容')
        expect(page.locator('#materials-status')).not_to_be_visible()
    finally:
        page.close()
