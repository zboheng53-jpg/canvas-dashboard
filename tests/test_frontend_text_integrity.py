from pathlib import Path
import re

import settings


def test_index_template_has_valid_visible_chinese_and_no_leaked_tags():
    templates = Path(__file__).parents[1] / "frontend" / "templates"
    index_text = (templates / "index.html").read_text(encoding="utf-8")
    sidebar_text = (templates / "dashboard" / "_academic_sidebar.html").read_text(encoding="utf-8")
    views_text = (templates / "dashboard" / "_placeholder_views.html").read_text(encoding="utf-8")
    text = "\n".join((index_text, sidebar_text, views_text))

    assert "&#24453;&#21150;&#28165;&#21333;" in index_text
    assert "今日总览" in sidebar_text
    assert "连接与同步" in sidebar_text
    assert "日历订阅" in sidebar_text
    assert "退出登录" in sidebar_text
    assert "智慧树" in views_text
    assert "Apple Calendar 订阅" in views_text
    assert "${data.week}" in index_text
    assert "\\u00b0C" in index_text

    bad_fragments = [
        "?/span>",
        "?/a>",
        "\u7ed7?{data.week}",
        "\u9a9e?",
        "\u9354\u72ba\u6d47",
        "\u5bf0\u546d",
        "\u95ab\u20ac",
        "\u63b3",
        "\u8133",
        "\u9983",
    ]
    for fragment in bad_fragments:
        assert fragment not in text


def test_default_term_label_is_readable_chinese():
    assert settings.TERM_LABEL == "2025-2026\u5b66\u5e74 \u7b2c\u4e8c\u5b66\u671f"


def test_dashboard_template_never_treats_production_domain_as_demo():
    index_text = (Path(__file__).parents[1] / "frontend" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "canvas-dashboard.xyz" not in index_text


def test_todo_frontend_keeps_platform_sync_and_dynamic_content_boundaries():
    templates = Path(__file__).parents[1] / "frontend" / "templates"
    index_text = (templates / "index.html").read_text(encoding="utf-8")
    login_text = (templates / "login_zhixuemeng.html").read_text(encoding="utf-8")

    expected_syncs = {
        "fetchCanvasTodos": "canvas",
        "fetchHaokeTodos": "haoke",
        "fetchZhixuemengTodos": "zhixuemeng",
        "fetchZhihuishuTodos": "zhihuishu",
    }
    for function_name, platform in expected_syncs.items():
        body = re.search(
            rf"async function {function_name}\(\) \{{(.*?)(?=\n    (?:async )?function )",
            index_text,
            re.DOTALL,
        )
        assert body, f"missing {function_name}"
        assert f"recordPlatformSync('{platform}', result);" in body.group(1)

    custom_body = re.search(
        r"async function fetchCustomTodos\(\) \{(.*?)(?=\n    (?:async )?function )",
        index_text,
        re.DOTALL,
    )
    assert custom_body
    assert "recordPlatformSync(" not in custom_body.group(1)
    assert index_text.count("saveInlineEdit(id, 'multi', { text: taskText, labels });") == 1
    assert "function sanitizeExternalUrl(value)" in index_text
    assert "['https:', 'http:'].includes(url.protocol)" in index_text
    assert 'rel="noopener noreferrer"' in index_text

    for text in (index_text, login_text):
        assert "function populateZhixuemengCourseSelect" in text
        assert "option.textContent" in text
        assert 'select.innerHTML = \'<option value="">全部课程</option>\'' not in text


def test_dashboard_p1_feature_modules_own_new_event_bindings_and_request_contract():
    project_root = Path(__file__).parents[1]
    assets = project_root / "frontend" / "assets" / "js"
    index_text = (project_root / "frontend" / "templates" / "index.html").read_text(encoding="utf-8")
    views_text = (project_root / "frontend" / "templates" / "dashboard" / "_placeholder_views.html").read_text(encoding="utf-8")

    api_text = (assets / "api" / "client.js").read_text(encoding="utf-8")
    assert "function requestJson" in api_text
    assert "DashboardRequestError" in api_text
    assert "global.dashboardApi" in api_text

    for feature in ("todos", "connections", "schedule", "settings"):
        module_text = (assets / "features" / f"{feature}.js").read_text(encoding="utf-8")
        assert "addEventListener" in module_text
        assert f"js/features/{feature}.js" in index_text

    assert 'onchange="setTodoSourceFilter' not in index_text
    assert "onsubmit=\"handleScheduleFormSubmit(event)\"" not in views_text
    assert "onsubmit=\"event.preventDefault(); deleteCurrentAccount();\"" not in views_text
    assert "dashboardApi.requestJson('/api/apple-calendar/subscription'" in index_text
    assert "dashboardApi.requestJson('/api/account'" in index_text


def test_schedule_login_and_connection_primary_actions_have_shared_contract():
    project_root = Path(__file__).parents[1]
    views_text = (project_root / "frontend" / "templates" / "dashboard" / "_placeholder_views.html").read_text(
        encoding="utf-8"
    )
    shell_css = (project_root / "frontend" / "assets" / "css" / "dashboard-shell.css").read_text(encoding="utf-8")

    assert 'id="schedule-refresh-button" onclick="openTongjiLoginSession()">统一身份认证登录<' in views_text
    assert views_text.count("connection-primary-action") == 3
    assert ".connection-primary-action" in shell_css
    assert "button.connection-primary-action:disabled" in shell_css


def test_v103_overview_and_project_task_cards_keep_the_refined_card_hierarchy():
    """重设计后的卡片层级规则收敛在 design-system.css（v103 legacy 规则已下线）。"""
    css_text = (Path(__file__).parents[1] / "frontend" / "assets" / "css" / "design-system.css").read_text(
        encoding="utf-8"
    )

    expected_rules = [
        "功能页重设计落地",
        ".project-task-group {",
        ".project-task-item {",
        ".project-next-action-card {",
        ".connections-layout {",
        ".calendar-subscription-layout {",
        ".settings-danger-zone {",
    ]
    for rule in expected_rules:
        assert rule in css_text
