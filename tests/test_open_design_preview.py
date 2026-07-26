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
    assert 'href="../assets/css/style.css"' in html
    assert 'src="../assets/js/projects.js"' in html
    assert "window.__OPEN_DESIGN_PREVIEW__ = true" in html
    assert 'src="../assets/js/open-design-mock.js"' in html


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

            page.get_by_role("button", name="长期项目").click()
            page.locator("#project-detail").get_by_text("自动化课程设计").wait_for()
            page.get_by_role("button", name="日程与课表").click()
            page.locator("#dashboard-view-schedule").wait_for()
            page.locator("#schedule-management-summary").get_by_text("已导入 1 门课程").wait_for(state="attached")
            assert not browser_errors
        finally:
            browser.close()
