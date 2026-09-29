"""Appearance persists locally without changing data or desktop geometry."""
import pytest
from playwright.sync_api import expect

import browser_env
from test_frontend_playwright import register_dashboard_user


def _set_theme(page, theme):
    page.evaluate("switchDashboardView('settings')")
    page.locator(f'[data-appearance-theme="{theme}"]').click()


def test_theme_persists_across_pages_and_tabs_without_rearranging_dashboard(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    register_dashboard_user(page, live_app, "appearancetheme")
    card = page.locator('.listcard')
    before = card.bounding_box()
    original_color = card.evaluate('(e) => getComputedStyle(e).backgroundColor')
    source_color = page.locator('.ui-source--canvas').first.evaluate('(e) => getComputedStyle(e, "::before").backgroundColor')
    other = page.context.new_page()
    other.goto(live_app)
    _set_theme(page, 'moss')
    expect(other.locator('html')).to_have_attribute('data-theme', 'moss')
    page.evaluate("switchDashboardView('overview')")
    browser_env.wait_for_layout_settled(page)
    after = card.bounding_box()
    # 主题切换只改配色，几何必须逐像素一致；<1px 仅容纳亚像素取整
    assert all(abs(before[key] - after[key]) < 1 for key in ('x', 'y', 'width', 'height'))
    assert card.evaluate('(e) => getComputedStyle(e).backgroundColor') != original_color
    expect(card).to_have_css('background-color', 'rgb(255, 254, 249)')
    expect(page.locator('#academic-sidebar')).to_have_css('background-color', 'rgb(255, 254, 249)')
    assert page.locator('.ui-source--canvas').first.evaluate('(e) => getComputedStyle(e, "::before").backgroundColor') == source_color
    page.reload()
    expect(page.locator('html')).to_have_attribute('data-theme', 'moss')
    page.goto(f'{live_app}/login')
    expect(page.locator('html')).to_have_attribute('data-theme', 'moss')
    page.goto(live_app)
    _set_theme(page, 'blue')
    expect(other.locator('html')).to_have_attribute('data-theme', 'blue')
    page.evaluate("switchDashboardView('overview')")
    expect(card).to_have_css('background-color', original_color)


def test_theme_handles_unavailable_local_storage(live_app, browser):
    page = browser.new_page()
    register_dashboard_user(page, live_app, 'appearancestorage')
    page.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('blocked');}})")
    page.reload()
    expect(page.locator('html')).to_have_attribute('data-theme', 'blue')
    _set_theme(page, 'moss')
    expect(page.locator('html')).to_have_attribute('data-theme', 'moss')
    expect(page.locator('#appearance-status')).to_contain_text('未允许保存')


@pytest.mark.parametrize('width', [390, 768])
def test_mobile_composer_retains_draft_and_failure_then_collapses_after_success(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844}, reduced_motion="reduce")
    register_dashboard_user(page, live_app, f'appearancephone{width}')
    toggle = page.locator('#mobile-add-toggle')
    form = page.locator('#add-todo-form')
    expect(form).to_be_hidden()
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    expect(page.locator('.todo-row').first).to_be_visible()
    page.wait_for_function("""() => {
        const row = document.querySelector('.todo-row');
        const dock = document.querySelector('.mobile-bottom-nav');
        return row?.checkVisibility() && dock?.checkVisibility()
            && row.getBoundingClientRect().bottom <= dock.getBoundingClientRect().top;
    }""")
    toggle.click()
    expect(page.locator('#new-todo-input')).to_be_focused()
    page.fill('#new-todo-input', '主题验收：保留草稿')
    page.keyboard.press('Escape')
    expect(form).to_be_hidden()
    toggle.click()
    expect(page.locator('#new-todo-input')).to_have_value('主题验收：保留草稿')
    page.route('**/api/custom/todos', lambda route: route.fulfill(status=503, json={'error': '暂时无法保存'}))
    page.locator('#btn-add-todo').click()
    expect(page.locator('#add-todo-error')).to_contain_text('暂时无法保存')
    expect(form).to_be_visible()
    expect(page.locator('#new-todo-input')).to_have_value('主题验收：保留草稿')
    page.unroute('**/api/custom/todos')
    page.locator('#btn-add-todo').click()
    expect(form).to_be_hidden()
    expect(page.locator('.todo-row', has_text='主题验收：保留草稿')).to_be_visible()
    expect(toggle).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    page.set_viewport_size({'width': 1440, 'height': 900})
    expect(form).to_be_visible()
    expect(toggle).to_be_hidden()


def test_entry_fade_finishes_and_respects_reduced_motion(live_app, browser):
    page = browser.new_page(reduced_motion='no-preference')
    register_dashboard_user(page, live_app, 'appearancemotion')
    workspace = page.locator('.workspace-stack')
    expect(workspace).to_have_css('animation-name', 'workspace-arrive')
    expect(workspace).to_have_css('animation-duration', '0.7s')
    # Replay only within this test to inspect the actual start and middle frames.
    workspace.evaluate('''e => {
        e.style.animationName = 'none'; void e.offsetWidth;
        e.style.animationName = '';
        const animation = e.getAnimations()[0];
        animation.pause(); animation.currentTime = 0;
    }''')
    expect(workspace).to_have_css('opacity', '0')
    expect(workspace).to_have_css('transform', 'matrix(1, 0, 0, 1, 0, 16)')
    workspace.evaluate('e => { e.getAnimations()[0].currentTime = 350; }')
    assert 0 < float(workspace.evaluate('e => getComputedStyle(e).opacity')) < 1
    workspace.evaluate('e => e.getAnimations()[0].play()')
    page.wait_for_function("document.getAnimations().filter(a => a.animationName === 'workspace-arrive').length === 0")
    expect(workspace).to_have_css('opacity', '1')
    expect(workspace).to_have_css('transform', 'none')
    page.locator('[data-dashboard-view="guide"]').click()
    page.locator('[data-open-view="overview"]').first.click()
    assert page.evaluate("document.getAnimations().filter(a => a.animationName === 'workspace-arrive').length") == 0
    page.emulate_media(reduced_motion='reduce')
    expect(workspace).to_have_css('animation-name', 'none')
