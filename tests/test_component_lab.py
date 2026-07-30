from pathlib import Path

import pytest

import app as dashboard_app
from scripts.export_component_lab_preview import export_component_lab_preview


def _authenticated_client():
    dashboard_app.app.config.update(TESTING=True)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session:
        session["username"] = "alice"
    return client


def test_component_lab_requires_login():
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        response = client.get("/component-lab")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_component_lab_renders_required_component_families():
    with _authenticated_client() as client:
        response = client.get("/component-lab")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    required_labels = [
        "字体层级",
        "颜色与表面",
        "按钮",
        "图标按钮",
        "输入与表单",
        "标签与状态",
        "反馈与提示",
        "加载与空状态",
        "卡片、列表与导航",
        "弹窗",
    ]
    for label in required_labels:
        assert label in html
    assert 'href="/static/css/component-lab.css"' in html
    assert 'src="/static/js/component-lab.js"' in html
    assert html.count('data-candidate="action-') == 3
    assert html.index('id="forms"') < html.index("日期、下拉与复选框状态矩阵") < html.index('id="status"')


def test_export_component_lab_preview_uses_relative_assets(tmp_path: Path):
    previous_testing = dashboard_app.app.config["TESTING"]
    dashboard_app.app.config.update(TESTING=False)
    try:
        output = export_component_lab_preview(tmp_path / "component-lab.html")
        html = output.read_text(encoding="utf-8")
    finally:
        restored_testing = dashboard_app.app.config["TESTING"]
        dashboard_app.app.config.update(TESTING=previous_testing)

    assert 'href="../assets/css/component-lab.css"' in html
    assert 'src="../assets/js/component-lab.js"' in html
    assert "/static/" not in html
    assert restored_testing is False


def test_component_lab_modal_and_candidate_selection_work_in_static_preview(tmp_path: Path):
    playwright_api = pytest.importorskip("playwright.sync_api")
    preview_root = tmp_path / "frontend"
    assets_source = Path(__file__).parents[1] / "frontend" / "assets"
    import shutil

    shutil.copytree(assets_source, preview_root / "assets")
    output = export_component_lab_preview(preview_root / "open-design-preview" / "component-lab.html")

    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        browser_errors = []
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        try:
            page.goto(output.as_uri())
            assert page.get_by_label("候选 A：近白描边").is_checked()
            assert page.locator('[data-candidate="action-a"]').get_attribute("data-selected") == "true"
            assert "Noto Serif SC" in page.locator(".lab-section-heading h2").first.evaluate(
                "element => getComputedStyle(element).fontFamily"
            )
            assert "Noto Serif SC" in page.locator(".lab-specimen-heading h3").first.evaluate(
                "element => getComputedStyle(element).fontFamily"
            )
            assert page.evaluate("document.documentElement.scrollWidth") == 1440

            page.get_by_role("button", name="打开弹窗示例").click()
            dialog = page.get_by_role("dialog", name="新建学习任务")
            assert dialog.is_visible()
            page.keyboard.press("Escape")
            assert dialog.is_hidden()

            page.get_by_label("候选 B：浅蓝弱背景").check()
            assert page.locator('[data-candidate="action-b"]').get_attribute("data-selected") == "true"
            assert not browser_errors
        finally:
            browser.close()
