"""Phone overview favors frequent tasks while keeping the desktop workspace intact."""
from datetime import timedelta
import re

import pytest
from playwright.sync_api import expect

import project_store
from test_frontend_playwright import register_dashboard_user


def create_todo(page, live_app, text, due_date, **extra):
    response = page.request.post(
        f'{live_app}/api/custom/todos',
        data={'text': text, 'due_date': due_date, **extra},
        headers={'X-CSRF-Token': page.evaluate('window.CSRF_TOKEN')},
    )
    assert response.ok, response.text()
    return response.json()


@pytest.mark.parametrize('width', [320, 360, 390, 430, 768])
@pytest.mark.parametrize('theme', ['blue', 'moss'])
def test_mobile_overview_has_aligned_readable_content(live_app, browser, test_now, width, theme):
    page = browser.new_page(viewport={'width': width, 'height': 844}, reduced_motion='reduce')
    username = f'compact{width}{theme}'
    register_dashboard_user(page, live_app, username)
    long_title = '核对自动控制原理实验报告中的参数、图表和结论，并整理下一次讨论的问题'
    tomorrow = (test_now.date() + timedelta(days=1)).isoformat()
    create_todo(page, live_app, long_title, tomorrow)
    create_todo(page, live_app, '没有截止日期的资料整理', None)
    project = project_store.create_project(username, {'name': '手机项目'})
    project_store.create_task(username, project['id'], {
        'name': '项目今天的计划', 'planned_on': test_now.date().isoformat(),
        'is_next_action': True,
    })
    page.reload()
    page.evaluate("switchDashboardView('settings')")
    page.locator(f'[data-appearance-theme="{theme}"]').click()
    page.evaluate("switchDashboardView('overview')")
    expect(page.locator('.todo-row', has_text=long_title)).to_be_visible()
    expect(page.locator('.todo-row', has_text='项目今天的计划')).to_be_visible()
    expect(page.locator('.todo-row', has_text='项目今天的计划').locator('.todo-date-mobile')).to_have_text('计划 今天')
    expect(page.locator('.todo-row', has_text='没有截止日期的资料整理').locator('.todo-date-mobile')).to_have_text('未设截止')

    # Take all measurements in one frame; asynchronous platform refresh can replace rows.
    page.wait_for_function("""() => {
      const rows = [...document.querySelectorAll('.todo-row')].filter(e => e.checkVisibility());
      return rows.length >= 4 && rows.every(row => {
        const source = row.querySelector('.item-source-badge').getBoundingClientRect();
        const due = row.querySelector('.item-due').getBoundingClientRect();
        const title = row.querySelector('.item-title');
        return Math.abs(source.bottom - due.bottom) <= 1
          && source.right <= due.left + 1
          && title.scrollWidth <= title.clientWidth + 1
          && row.getBoundingClientRect().right <= innerWidth
          && getComputedStyle(row.querySelector('.biz-todo__meta')).display === 'none';
      }) && document.documentElement.scrollWidth <= innerWidth;
    }""")
    title = page.locator('.todo-row', has_text=long_title).locator('.item-title')
    if width <= 430:
        assert title.bounding_box()['height'] >= 40
    expect(page.locator('.mobile-bottom-nav .mobile-nav-item')).to_have_count(3)
    expect(page.locator('.weather-detail')).to_be_hidden()
    expect(page.locator('.opt1-time')).to_be_hidden()
    page.wait_for_function("""() => {
      const title = document.querySelector('.listcard h2').getBoundingClientRect();
      const button = document.querySelector('#mobile-add-toggle').getBoundingClientRect();
      return title.right < button.left && title.top < button.bottom && title.bottom > button.top;
    }""")
    page.locator('#mobile-add-toggle').click()
    expect(page.locator('#new-todo-input')).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth') <= width
    page.close()


@pytest.mark.parametrize('width', [320, 390, 768])
def test_mobile_project_tasks_keep_title_space_and_working_actions(live_app, browser, test_now, width):
    page = browser.new_page(viewport={'width': width, 'height': 844})
    username = f'phoneproject{width}'
    register_dashboard_user(page, live_app, username)
    project = project_store.create_project(username, {'name': '手机项目入口'})
    title = '完成听力诊断与核心词复习，并记录需要再次练习的内容'
    task = project_store.create_task(username, project['id'], {
        'name': title, 'planned_on': test_now.date().isoformat(),
        'details': '保留完整项目资料', 'is_next_action': True,
    })
    page.reload()
    page.locator('[data-mobile-tab="projects"]').click()
    row = page.locator(f'.project-task-item[data-task-id="{task["id"]}"]')
    expect(row).to_be_visible()
    row.scroll_into_view_if_needed()
    assert row.evaluate("""e => {
      const title = e.querySelector('.project-task-name-btn');
      const actions = e.querySelector('.project-task-actions').getBoundingClientRect();
      const rect = title.getBoundingClientRect();
      return rect.width > 160 && title.scrollWidth <= title.clientWidth + 1
        && actions.top >= rect.bottom && actions.right <= innerWidth
        && document.documentElement.scrollWidth <= innerWidth;
    }""")
    row.locator('.project-task-name-btn').click()
    expect(page.locator('#action-detail-dialog')).to_contain_text('保留完整项目资料')
    page.get_by_role('button', name='关闭事项详情').click()
    row.get_by_title('编辑', exact=True).click()
    expect(page.locator('#project-task-modal')).to_be_visible()
    assert page.locator('#project-task-modal .project-modal-card').bounding_box()['width'] <= width
    page.locator('#project-task-modal .project-modal-close').click()
    row.locator('input[type="checkbox"]').check()
    expect(page.locator('#project-detail .project-completed-tasks')).to_contain_text('已完成 1 项')
    page.locator('[data-mobile-tab="schedule"]').click()
    expect(page.locator('.period-day')).to_have_count(7)
    expect(page.locator('.period-cell:visible')).to_have_count(4)
    assert page.locator('.period-day').evaluate_all(
        'nodes => nodes.every(e => e.getBoundingClientRect().right <= innerWidth)'
    )
    first_day = page.locator('.period-day').first
    first_day.click()
    expect(first_day).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('.period-cell:visible')).to_have_count(4)
    page.close()


def test_mobile_dates_details_and_completion_remain_usable(live_app, browser, test_now):
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    register_dashboard_user(page, live_app, 'compactactions')
    create_todo(page, live_app, '手机日期编辑', test_now.date().isoformat(), details='完整资料仍然可以查看')
    page.reload()
    row = page.locator('.todo-row', has_text='手机日期编辑')
    expect(row).to_be_visible()
    row.locator('.editable-due').click()
    editor = row.locator('.inline-edit-date-input')
    expect(editor).to_have_value(test_now.date().isoformat())
    editor.fill((test_now.date() + timedelta(days=1)).isoformat())
    page.evaluate('renderUnifiedList()')
    expect(editor).to_have_value((test_now.date() + timedelta(days=1)).isoformat())
    editor.press('Enter')
    expect(row.locator('.todo-date-mobile')).to_have_text('截止 明天')
    row.locator('.mobile-action-trigger').click()
    actions = row.locator('.item-mobile-actions')
    expect(actions).to_be_visible()
    for button in actions.locator('button').all():
        rect = button.bounding_box()
        assert rect['height'] >= 44 and rect['width'] >= 36
    actions.get_by_role('button', name='详情', exact=True).click()
    dialog = page.locator('#action-detail-dialog')
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text('完整资料仍然可以查看')
    assert dialog.bounding_box()['width'] <= 390
    dialog.get_by_role('button', name='关闭事项详情').click()
    with page.expect_response(lambda r: '/api/custom/todos/' in r.url and r.request.method == 'PUT') as saved:
        actions.locator('.btn-dismiss').click()
    assert saved.value.ok
    expect(row).to_have_class(re.compile(r'\bdismissed\b'))
    page.close()


def test_subtask_draft_survives_refresh_and_failed_save(live_app, browser, test_now):
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    register_dashboard_user(page, live_app, 'compactdraft')
    create_todo(page, live_app, '子任务草稿', test_now.date().isoformat())
    page.reload()
    item = page.locator('.todo-row-wrap', has_text='子任务草稿')
    item.locator('.subtask-toggle').click()
    field = item.locator('.subtask-add-input')
    field.fill('正在记录的步骤')
    page.evaluate('renderUnifiedList()')
    expect(field).to_have_value('正在记录的步骤')
    expect(field).to_be_focused()
    page.route('**/api/custom/todos/*', lambda route: (
        route.fulfill(status=503, json={'error': '暂时无法保存'})
        if route.request.method == 'PUT' else route.continue_()
    ))
    page.once('dialog', lambda dialog: dialog.dismiss())
    with page.expect_response(lambda r: '/api/custom/todos/' in r.url and r.request.method == 'PUT') as failed:
        field.press('Enter')
    assert failed.value.status == 503
    expect(field).to_have_value('正在记录的步骤')
    page.unroute('**/api/custom/todos/*')
    field.press('Enter')
    expect(item.locator('.subtask-text')).to_have_text('正在记录的步骤')
    expect(field).to_have_value('')
    page.close()
