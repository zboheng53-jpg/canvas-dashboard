from pathlib import Path

import settings


def test_index_template_has_valid_visible_chinese_and_no_leaked_tags():
    templates = Path(__file__).parents[1] / "templates"
    index_text = (templates / "index.html").read_text(encoding="utf-8")
    sidebar_text = (templates / "dashboard" / "_academic_sidebar.html").read_text(encoding="utf-8")
    views_text = (templates / "dashboard" / "_placeholder_views.html").read_text(encoding="utf-8")
    text = "\n".join((index_text, sidebar_text, views_text))

    assert "&#24453;&#21150;&#28165;&#21333;" in index_text
    assert "今日总览" in sidebar_text
    assert "连接与同步" in sidebar_text
    assert "Apple Calendar" in sidebar_text
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


def test_schedule_login_and_connection_primary_actions_have_shared_contract():
    project_root = Path(__file__).parents[1]
    views_text = (project_root / "templates" / "dashboard" / "_placeholder_views.html").read_text(
        encoding="utf-8"
    )
    shell_css = (project_root / "static" / "dashboard-shell.css").read_text(encoding="utf-8")

    assert 'id="schedule-refresh-button" onclick="openTongjiLoginSession()">统一身份认证登录<' in views_text
    assert views_text.count("connection-primary-action") == 3
    assert ".connection-primary-action" in shell_css
    assert "button.connection-primary-action:disabled" in shell_css
