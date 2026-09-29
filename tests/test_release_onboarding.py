import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

import browser_env
from test_frontend_playwright import register_dashboard_user


@pytest.mark.parametrize('width', [1440, 390, 320])
def test_guide_navigation_dates_and_new_todo(live_app, browser, width):
    page = browser.new_page(viewport={'width': width, 'height': 950})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register_dashboard_user(page, live_app, f'guide{width}')
    expect(page.locator('.todo-row', has_text='Canvas seeded')).to_be_visible()
    if width > 768:
        expect(page.locator('.todo-row', has_text='Canvas seeded').locator('.todo-date-desktop')).to_have_text('2099-07-10')
    if width <= 960:
        page.locator('#mobile-menu-toggle').click()
    page.locator('[data-dashboard-view="guide"]').click()
    expect(page.locator('#guide-title')).to_be_visible()
    expect(page.locator('#dashboard-right-rail')).to_be_hidden()
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    toc = page.get_by_role('navigation', name='上手指南目录')
    expect(toc.locator('a')).to_have_count(11)
    for anchor in toc.locator('a').all():
        target = anchor.get_attribute('href')
        anchor.click()
        expect(page.locator(target).locator('h2')).to_be_in_viewport()
    expect(page.get_by_role('link', name='GitHub 开源仓库')).to_have_attribute(
        'href', 'https://github.com/zboheng53-jpg/canvas-dashboard')
    expect(page.locator('.guide-entries .guide-entry-icon svg')).to_have_count(7)
    expect(page.locator('.guide-specimen')).to_have_count(7)
    expect(page.locator('.guide-platforms .ui-badge--source')).to_have_count(6)
    page.wait_for_function(
        "Array.from(document.querySelectorAll('.guide-shot img')).every(img => img.naturalWidth > 0)")
    shots = page.locator('.guide-shot img')
    expect(shots).to_have_count(3)
    for index in range(3):
        expect(shots.nth(index)).to_have_attribute('src', re.compile(r'/static/guide/canvas-calendar-[\w-]+\.jpg'))
    expect(page.get_by_role('link', name='iPhone / iPad 教程')).to_have_attribute(
        'href', 'https://support.apple.com/zh-cn/102301')
    expect(page.get_by_role('link', name='Google 日历教程（电脑添加）')).to_have_attribute(
        'href', 'https://support.google.com/calendar/answer/37100?hl=zh-CN')
    expect(page.locator('#guide-connections')).to_contain_text('右下角「日历馈送」')
    faq = page.locator('#guide-help details')
    expect(faq).to_have_count(3)
    expect(faq.first.locator('a')).to_have_attribute('href', '#guide-connections')
    page.get_by_role('link', name='返回顶部').click()
    expect(toc.locator('a').first).to_be_in_viewport()
    expect(page.locator('#guide-title')).to_be_in_viewport()
    artifacts = os.environ.get('CANVAS_TEST_ARTIFACTS')
    if artifacts:
        page.screenshot(path=str(Path(artifacts) / f'guide-{width}.png'))
    page.locator('[data-open-view="overview"]').first.click()
    expect(page.locator('#dashboard-view-overview')).to_be_visible()
    if width <= 768:
        page.locator('#mobile-add-toggle').click()
    page.fill('#new-todo-input', '指南验收：写实验报告')
    page.click('#btn-add-todo')
    expect(page.locator('.todo-row', has_text='指南验收：写实验报告')).to_be_visible()
    assert errors == []


def test_registration_can_be_paused_without_blocking_login(isolated_data, monkeypatch):
    import app
    import settings
    monkeypatch.setattr(settings, 'REGISTRATION_ENABLED', False)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session['_csrf_token'] = 'test'
    response = client.post('/api/auth/register', json={'username': 'newuser', 'password': 'strong-password'}, headers={'X-CSRF-Token': 'test'})
    assert response.status_code == 403
    assert response.json['code'] == 'registration_closed'
    assert client.get('/login').status_code == 200
    assert '暂时停止新注册' in client.get('/register').get_data(as_text=True)


@pytest.mark.parametrize('width', [1440, 390])
def test_capacity_guard_keeps_showcase_and_explains_closure(live_app, browser, width, monkeypatch):
    import auth
    import capacity_guard
    import settings

    monkeypatch.setattr(settings, 'CAPACITY_MAX_TOTAL_USERS', 1)
    monkeypatch.setattr(settings, 'CAPACITY_MAX_ACTIVE_USERS', 0)
    monkeypatch.setattr(settings, 'CAPACITY_MAX_CONNECTED_PLATFORMS', 0)
    capacity_guard.reset_cache()
    assert auth.register('capacityfull', 'password1')[0]

    page = browser.new_page(viewport={'width': width, 'height': 950})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(f'{live_app}/register')

    notice = page.locator('#register-closed-notice')
    expect(notice).to_be_visible()
    expect(page.locator('#register-form')).to_have_count(0)
    expect(notice).to_contain_text('用户上限')
    expect(notice).to_contain_text('谢谢你的期待与谅解')
    expect(notice.locator('.auth-capacity-body p')).to_have_count(2)
    expect(notice.locator('.auth-capacity-note')).to_contain_text('已有账号不受影响')
    expect(page.locator('.auth-landing-hero')).to_be_visible()
    expect(page.locator('.auth-landing-examples')).to_be_visible()
    expect(page.locator('.auth-privacy-panel')).to_be_visible()
    expect(page.get_by_role('link', name='直接登录')).to_be_visible()
    browser_env.wait_for_layout_settled(page)
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    assert errors == []

    page.goto(f'{live_app}/login')
    expect(page.get_by_role('link', name='查看说明')).to_be_visible()
    assert errors == []

    artifacts = os.environ.get('CANVAS_TEST_ARTIFACTS')
    if artifacts:
        page.goto(f'{live_app}/register')
        page.wait_for_function(
            "document.getAnimations().filter(a => a.animationName === 'showcase-arrive').length === 0")
        page.screenshot(path=str(Path(artifacts) / f'register-capacity-{width}.png'), full_page=True)


def test_subtask_save_survives_concurrent_list_refresh(live_app, browser):
    page = browser.new_page()
    register_dashboard_user(page, live_app, 'subtaskrefresh')
    page.fill('#new-todo-input', '刷新时保存子任务')
    page.click('#btn-add-todo')
    row = page.locator('.todo-row-wrap', has_text='刷新时保存子任务')
    row.locator('.subtask-toggle').click()

    def refresh_before_save(route):
        if route.request.method == 'PUT' and 'subtasks' in (route.request.post_data_json or {}):
            # Replaces the in-memory records while the write is in flight.
            page.evaluate('fetchCustomTodos()')
        route.continue_()

    page.route('**/api/custom/todos/*', refresh_before_save)
    row.locator('.subtask-add-input').fill('必须保留的步骤')
    row.locator('.subtask-add-input').press('Enter')
    expect(row.locator('.subtask-text')).to_have_text('必须保留的步骤')
    page.reload()
    row.locator('.subtask-toggle').click()
    expect(row.locator('.subtask-text')).to_have_text('必须保留的步骤')


@pytest.mark.parametrize('width', [1440, 390, 320])
def test_public_showcase_and_auth_are_usable(live_app, browser, width):
    # 本用例专门验证入场动效生命周期（animation-name 与 reduced-motion 覆写），
    # 因此显式要求 no-preference，跳过共享上下文的动效冻结。
    page = browser.new_page(viewport={'width': width, 'height': 950}, reduced_motion='no-preference')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    for path in ('login', 'register'):
        page.goto(f'{live_app}/{path}')
        expect(page.locator(f'#{path}-form')).to_be_visible()
        expect(page.locator('.auth-landing-hero')).to_have_css('animation-name', 'showcase-arrive')
        page.wait_for_function("document.getAnimations().filter(a => a.animationName === 'showcase-arrive').length === 0")
        assert page.locator(f'#{path}-form button').bounding_box()['y'] < 950
        for theme in ('blue', 'moss'):
            page.locator(f'[data-appearance-theme="{theme}"]').click()
            expect(page.locator('html')).to_have_attribute('data-theme', theme)
            assert page.evaluate('document.documentElement.scrollWidth') <= width
            artifacts = os.environ.get('CANVAS_TEST_ARTIFACTS')
            if artifacts:
                page.screenshot(path=str(Path(artifacts) / f'{path}-{width}-{theme}.png'), full_page=True)
        page.emulate_media(reduced_motion='reduce')
        expect(page.locator('.auth-landing-hero')).to_have_css('animation-name', 'none')
        page.emulate_media(reduced_motion='no-preference')
        assert errors == []


@pytest.mark.parametrize('width', [1440, 390])
def test_contextual_guide_links_and_connection_disclosures(live_app, browser, width):
    page = browser.new_page(viewport={'width': width, 'height': 950})
    register_dashboard_user(page, live_app, f'contextguide{width}')

    def navigate(view):
        if width <= 960:
            page.locator('#mobile-menu-toggle').click()
        page.locator(f'[data-dashboard-view="{view}"]').click()

    navigate('connections')
    notes = page.locator('.connection-data-disclosure')
    expect(notes).to_have_count(6)
    assert notes.evaluate_all('(nodes) => nodes.every(node => !node.open)')
    canvas_note = page.locator('#detail-canvas .connection-data-disclosure')
    expect(canvas_note.locator('.connection-trust-card')).to_be_hidden()
    canvas_note.locator('summary').click()
    expect(canvas_note.locator('.connection-trust-card')).to_be_visible()
    canvas_note.locator('summary').click()
    expect(canvas_note.locator('.connection-trust-card')).to_be_hidden()
    assert canvas_note.locator('summary').evaluate('(node) => getComputedStyle(node).display') == 'list-item'
    artifacts = os.environ.get('CANVAS_TEST_ARTIFACTS')
    if artifacts:
        page.screenshot(path=str(Path(artifacts) / f'connection-disclosure-{width}.png'))
    page.locator('#detail-canvas a[data-open-view="guide"]').click()
    expect(page.locator('#guide-connections-title')).to_be_in_viewport()
    expect(page.locator('#guide-connections-title')).to_be_focused()
    navigate('calendar')
    page.locator('#dashboard-view-calendar a[data-open-view="guide"]').click()
    expect(page.locator('#guide-calendar-title')).to_be_in_viewport()
    expect(page.locator('#guide-calendar-title')).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    if width <= 960:
        page.locator('#mobile-menu-toggle').click()
    browser_env.wait_for_layout_settled(page)
    gaps = page.locator('.sidebar-nav-group').evaluate_all("""nodes => nodes.slice(1).map((n, i) =>
        n.getBoundingClientRect().top - nodes[i].getBoundingClientRect().bottom)""")
    # 导航分组间距应完全一致，<1px 只容纳亚像素取整
    assert max(gaps) - min(gaps) < 1
    artifacts = os.environ.get('CANVAS_TEST_ARTIFACTS')
    if artifacts:
        page.screenshot(path=str(Path(artifacts) / f'contextual-guide-{width}.png'))
