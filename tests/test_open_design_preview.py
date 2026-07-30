import shutil
from pathlib import Path

import pytest

from scripts.export_open_design_preview import export_preview


def test_export_open_design_preview_renders_jinja_and_uses_relative_assets(tmp_path: Path):
    output = export_preview(tmp_path / "index.html", username="预览同学")
    html = output.read_text(encoding="utf-8")

    assert "{% include" not in html
    assert "{{ username }}" not in html
    assert "预览同学" in html
    assert 'href="../assets/css/dashboard.css"' in html
    assert 'src="../assets/js/projects.js"' in html
    assert "window.__OPEN_DESIGN_PREVIEW__ = true" in html
    assert 'src="../assets/js/open-design-mock.js"' in html


def test_project_overview_initializes_on_production_hostname():
    script = (Path(__file__).parents[1] / "frontend" / "assets" / "js" / "projects.js").read_text(encoding="utf-8")

    assert "canvas-dashboard.xyz" not in script


def test_exported_preview_loads_project_and_schedule_mock_data(tmp_path: Path):
    playwright_api = pytest.importorskip("playwright.sync_api")
    preview_root = tmp_path / "frontend"
    shutil.copytree(Path(__file__).parents[1] / "frontend" / "assets", preview_root / "assets")
    output = export_preview(preview_root / "open-design-preview" / "index.html")

    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        browser_errors = []
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        try:
            page.goto(output.as_uri())
            assert page.evaluate("window.__OPEN_DESIGN_MOCK_READY__") is True
            assert page.evaluate("fetch('/api/projects').then((response) => response.json())")["projects"][0]["name"] == "自动化课程设计"
            try:
                page.locator("#project-overview-content").get_by_text("自动化课程设计").wait_for(timeout=3_000)
            except playwright_api.TimeoutError as error:
                raise AssertionError(f"Project fixture did not render: {browser_errors}") from error
            page.locator("#today-schedule-content strong").filter(has_text="自动控制原理").first.wait_for()

            dashboard_grid = page.locator(".dashboard-grid")
            assert dashboard_grid.evaluate(
                "element => getComputedStyle(element).gridTemplateColumns"
            ) == "240px 1152px"
            assert dashboard_grid.evaluate("element => getComputedStyle(element).gap") == "24px"
            workspace_stack = page.locator(".workspace-stack")
            assert workspace_stack.evaluate(
                "element => getComputedStyle(element).gridTemplateColumns"
            ) == "790px 340px"
            assert workspace_stack.evaluate("element => getComputedStyle(element).gap") == "22px"
            assert page.evaluate("document.documentElement.scrollWidth") == 1440

            dashboard_title = page.locator(".card.enter-main-card .header-left-group h2")
            assert "Noto Serif SC" in dashboard_title.evaluate(
                "element => getComputedStyle(element).fontFamily"
            )
            overview_card = page.locator("#project-overview-content .project-overview-main")
            assert overview_card.evaluate("element => getComputedStyle(element).backgroundColor") == "rgba(248, 250, 252, 0.72)"
            assert overview_card.evaluate("element => getComputedStyle(element).borderRadius") == "10px"
            schedule_row = page.locator("#today-schedule-content .today-schedule-row").first
            assert schedule_row.evaluate("element => getComputedStyle(element).backgroundColor") == "rgb(248, 250, 252)"
            assert schedule_row.locator("time").evaluate("element => getComputedStyle(element).fontSize") == "11.5px"

            page.get_by_role("button", name="长期项目").click()
            page.locator("#project-detail").get_by_text("自动化课程设计").wait_for()
            project_group_card = page.locator("#project-detail .project-group-card").first
            assert project_group_card.evaluate("element => getComputedStyle(element).backgroundColor") == "rgba(248, 250, 252, 0.72)"
            assert project_group_card.evaluate("element => getComputedStyle(element).borderRadius") == "10px"
            task_row = page.locator("#project-detail .project-task-row").first
            assert task_row.evaluate("element => getComputedStyle(element).backgroundColor") == "rgb(255, 255, 255)"
            page.get_by_role("button", name="日程与课表").click()
            page.locator("#dashboard-view-schedule").wait_for()
            page.locator("#schedule-management-summary").get_by_text("已导入 1 门课程").wait_for(state="attached")
            assert not browser_errors
        finally:
            browser.close()
