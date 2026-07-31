"""Automated visual regression and multi-viewport responsive test suite.

Validates Desktop (1440), Laptop (1024), Tablet (768), and Mobile (375) layouts.
"""
from pathlib import Path
import pytest
from playwright.sync_api import expect

SCREENSHOT_DIR = Path("tests/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


import uuid

def register_dashboard_user(page, live_app, prefix="vis"):
    uid = uuid.uuid4().hex[:6]
    username = f"{prefix}{uid}"[:20]
    page.goto(f"{live_app}/register")
    page.fill("#register-username", username)
    page.fill("#register-password", "password123")
    page.click("#register-form button")
    page.wait_for_selector(".dashboard-shell")
    return username


@pytest.mark.parametrize("viewport", [
    {"width": 1440, "height": 900, "name": "desktop"},
    {"width": 1024, "height": 768, "name": "laptop"},
    {"width": 768, "height": 1024, "name": "tablet"},
    {"width": 375, "height": 812, "name": "mobile"},
])
def test_responsive_layout_no_horizontal_overflow(live_app, browser, viewport):
    page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
    register_dashboard_user(page, live_app, f"overflow_{viewport['name']}")
    
    # 1. Overview panel check
    expect(page.locator(".dashboard-shell")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"]
    
    # Take visual snapshot
    screenshot_path = SCREENSHOT_DIR / f"overview_{viewport['name']}.png"
    page.screenshot(path=str(screenshot_path))
    assert screenshot_path.exists()
    
    # 2. Switch to Connections panel
    if viewport["width"] <= 768:
        page.click("#mobile-menu-toggle")
    page.click('[data-dashboard-view="connections"]')
    expect(page.locator("#dashboard-view-connections")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"]
    
    # 3. Switch to Settings panel
    if viewport["width"] <= 768:
        page.click("#mobile-menu-toggle")
    page.click('[data-dashboard-view="settings"]')
    expect(page.locator("#dashboard-view-settings")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"]
    
    page.close()
