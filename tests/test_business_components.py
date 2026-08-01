import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "frontend" / "assets" / "css"
TEMPLATES = ROOT / "frontend" / "templates"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_loads_business_composition_in_pages_layer():
    dashboard = read(CSS / "dashboard.css")
    assert '@import url("./business.css") layer(pages);' in dashboard


def test_business_layer_uses_tokens_without_specificity_escalation():
    business = read(CSS / "business.css")
    assert "!important" not in business
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", business)
    assert not re.search(r"\b(?:rgb|rgba|hsl|hsla)\s*\(", business)
    assert not re.search(r"(?m)^\s*#[A-Za-z_]", business)


def test_business_modules_compose_confirmed_base_components():
    dashboard = read(TEMPLATES / "index.html")
    placeholders = read(TEMPLATES / "dashboard" / "_placeholder_views.html")
    projects = read(ROOT / "frontend" / "assets" / "js" / "projects.js")

    expected_dashboard_fragments = (
        "ui-list-item ui-list-item--interactive todo-row",
        "ui-card ui-card--subtle todo-subtask-panel",
        "ui-list-item todo-subtask-row",
        "tl-item",
        "schedule-block",
    )
    for fragment in expected_dashboard_fragments:
        assert fragment in dashboard

    expected_project_fragments = (
        "ui-nav-item project-browser-item",
        "ui-card ui-card--subtle project-task-group",
        "ui-list-item ui-list-item--interactive ui-list-item--contained project-task-item",
    )
    for fragment in expected_project_fragments:
        assert fragment in projects

    expected_page_fragments = (
        "ui-nav-item ui-nav-item--source ui-source--canvas connection-platform-item",
        "ui-card calendar-subscription-workspace",
        "ui-card settings-summary-grid",
        "ui-card-section settings-item",
    )
    for fragment in expected_page_fragments:
        assert fragment in placeholders


def test_migrated_template_has_no_active_inline_visual_css():
    placeholders = read(TEMPLATES / "dashboard" / "_placeholder_views.html")
    assert "<style" not in placeholders
    assert not re.search(r"\sstyle\s*=", placeholders)


def test_preview_data_covers_long_and_large_todo_content():
    mock = read(ROOT / "frontend" / "assets" / "js" / "open-design-mock.js")
    assert "课程设计长标签验证" in mock
    assert "足够长的子任务文字" in mock
    assert "Array.from({ length: 12 }" in mock


def test_schedule_series_are_separate_from_status_and_source_colors():
    tokens = read(CSS / "tokens.css")
    for token in (
        "--color-series-course:",
        "--color-series-recurring:",
        "--color-series-one-off:",
    ):
        assert token in tokens

    business = read(CSS / "business.css")
    assert "var(--color-series-course)" in business
    assert "var(--color-series-recurring)" in business
    assert "var(--color-series-one-off)" in business
