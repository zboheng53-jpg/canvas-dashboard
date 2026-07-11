# Mobile Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the three requested phone-only alignment corrections without changing the desktop layout.

**Architecture:** CSS-only production change at the existing 768px breakpoint. Playwright asserts relative element positions at phone widths and preserves desktop behavior at 769px.

**Tech Stack:** CSS, pytest, Playwright Python.

---

### Task 1: Add failing alignment regression tests

**Files:**
- Modify: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Add the test.**

```python
@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_alignment_places_controls_on_the_right(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"alignment{width}")
    page.fill("#new-todo-input", "Alignment task #label")
    page.click("#add-todo-form button")

    item = page.locator(".unified-item-wrap").filter(has_text="Alignment task")
    expect(item).to_be_visible()
    label_box = item.locator(".item-labels").bounding_box()
    subtask_box = item.locator(".item-subtask-slot").bounding_box()
    heading_box = page.locator(".section-header h2").bounding_box()
    header_box = page.locator(".section-header").bounding_box()
    emoji_box = page.locator(".weather-emoji").bounding_box()
    temp_box = page.locator(".weather-temp").bounding_box()
    assert label_box is not None and subtask_box is not None
    assert heading_box is not None and header_box is not None
    assert emoji_box is not None and temp_box is not None
    assert subtask_box["x"] > label_box["x"]
    assert abs((heading_box["y"] + heading_box["height"] / 2) - (header_box["y"] + header_box["height"] / 2)) <= 8
    assert emoji_box["x"] < temp_box["x"]
    assert abs((emoji_box["y"] + emoji_box["height"] / 2) - (temp_box["y"] + temp_box["height"] / 2)) <= 2
```

- [ ] **Step 2: Verify red.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_alignment_places_controls_on_the_right -q`

Expected: failure because the subtask slot remains below labels and weather remains vertically stacked.

### Task 2: Apply phone-only alignment CSS

**Files:**
- Modify: `static/style.css:1090-1170`
- Test: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Add these overrides inside the existing `@media (max-width: 768px)` block.**

```css
.weather-left { flex-direction: row; align-items: center; gap: 6px; }
.section-header h2 { align-self: center; }
.unified-item {
  grid-template-areas:
    "source title more"
    "source due more"
    "source labels subtask"
    "source mobile-actions mobile-actions";
}
.item-subtask-slot { justify-self: end; align-self: center; }
```

- [ ] **Step 2: Verify green and desktop protection.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q`

Expected: all frontend Playwright tests pass.

- [ ] **Step 3: Run full verification and commit.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

Run: `git add static/style.css tests/test_frontend_playwright.py`

Run: `git commit -m "fix: align compact mobile controls"`
