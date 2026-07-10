# Mobile Responsive Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing dashboard URL usable in mobile browsers without changing desktop behavior, data, or APIs.

**Architecture:** Keep Flask routes, `templates/index.html`, and client JavaScript unchanged. Add responsive CSS at `max-width: 768px`, with Playwright regression tests using the existing authenticated live-app fixture.

**Tech Stack:** Flask, CSS, pytest, Playwright Python.

---

## File structure

- Modify: `static/style.css` — responsive header, form, unified-todo, and touch-target rules.
- Modify: `tests/test_frontend_playwright.py` — mobile browser layout tests.

### Task 1: Add failing mobile-layout regression tests

**Files:**
- Modify: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Add this test below `test_frontend_todo_heading_is_centered_in_header`.**

```python
def test_frontend_mobile_header_compacts_weather(live_app, browser):
    page = browser.new_page(viewport={"width": 375, "height": 844})
    register_dashboard_user(page, live_app, "mobileheader")

    expect(page.locator(".weather-desc")).to_be_hidden()
    expect(page.locator(".weather-detail")).to_be_hidden()
    assert page.locator(".weather-left").evaluate(
        "element => getComputedStyle(element).flexDirection"
    ) == "column"
```

- [ ] **Step 2: Run the test and verify the red state.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_header_compacts_weather -q`

Expected: `FAIL` because `.weather-desc` is visible before the responsive rule exists.

- [ ] **Step 3: Add this parameterized test immediately after the header test.**

```python
@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_todo_layout_is_compact_and_tappable(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"mobiletodo{width}")

    todo = page.locator(".unified-item")
    expect(todo).to_be_visible()
    assert todo.evaluate("element => getComputedStyle(element).display") == "grid"
    assert page.evaluate("document.documentElement.scrollWidth") <= width

    todo_input_box = page.locator("#new-todo-input").bounding_box()
    date_input_box = page.locator("#new-todo-due").bounding_box()
    assert todo_input_box is not None
    assert date_input_box is not None
    assert date_input_box["y"] >= todo_input_box["y"] + todo_input_box["height"]

    for selector in (".btn-flag", ".btn-dismiss", ".btn-delete"):
        button_box = todo.locator(selector).bounding_box()
        assert button_box is not None
        assert button_box["width"] >= 36
        assert button_box["height"] >= 36
```

- [ ] **Step 4: Run the test and verify the red state.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_todo_layout_is_compact_and_tappable -q`

Expected: three failures reporting `flex` rather than `grid`.

### Task 2: Implement the responsive CSS

**Files:**
- Modify: `static/style.css:1079-1128`
- Test: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Replace the existing `@media (max-width: 768px)` block with this CSS.**

```css
@media (max-width: 768px) {
  .dashboard { padding: 24px 14px 48px; }
  .card { padding: 16px; }
  .top-bar { flex-direction: row; align-items: flex-start; gap: 12px; }
  .top-bar .clock-section { min-width: 0; }
  .clock-section .time { font-size: 42px; }
  .clock-section .date-info { gap: 12px; flex-wrap: wrap; }
  .top-right-group { align-items: flex-end; align-self: flex-start; min-width: 48px; }
  .weather-card { flex-direction: column; align-items: flex-end; gap: 2px; }
  .weather-left { flex-direction: column; align-items: center; gap: 1px; }
  .weather-emoji { font-size: 26px; }
  .weather-temp { font-size: 32px; line-height: 1; }
  .weather-right { display: none; }
  .term-info { justify-content: flex-end; margin-top: 5px; font-size: 12px; text-align: right; }
  .section-header { flex-wrap: wrap; align-items: flex-start; gap: 8px; }
  .header-right { margin-left: auto; }
  .add-todo-form { display: grid; grid-template-columns: minmax(0, 1fr) 44px; flex-wrap: nowrap; }
  .add-todo-form #new-todo-input { grid-column: 1 / -1; min-width: 0; }
  .add-todo-form .date-input { grid-column: 1; width: 100%; }
  .add-todo-form button { grid-column: 2; width: 44px; }
  .item-course { display: none; }
  .unified-item {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas: "source title due" "source labels labels" "source subtask actions";
    align-items: start;
    column-gap: 8px;
    row-gap: 4px;
    margin-left: -3px;
    margin-right: 0;
    padding: 10px 0 10px 12px;
  }
  .unified-item:hover { margin-left: -3px; margin-right: 0; padding-left: 12px; padding-right: 0; }
  .unified-item.urgent, .unified-item.approaching { padding-right: 0; }
  .item-source-badge { grid-area: source; align-self: start; }
  .item-title { grid-area: title; }
  .item-due { grid-area: due; align-self: start; font-size: 12px; }
  .item-labels { grid-area: labels; margin-top: 0; }
  .item-subtask-slot { grid-area: subtask; margin-right: 0; min-height: 36px; }
  .item-actions { grid-area: actions; justify-self: end; min-height: 36px; }
  .btn-flag, .btn-dismiss, .btn-delete, .subtask-toggle { width: 36px; height: 36px; padding: 0; }
  .login-cards { grid-template-columns: repeat(2, 1fr); }
  .platform-row { flex-direction: column; gap: 16px; }
  .subtask-panel { margin-left: 34px; margin-right: 0; }
  .subtask-upcoming-preview { margin-left: 34px; margin-right: 0; }
  .subtask-due-input { width: 100px; }
}
```

- [ ] **Step 2: Run both tests and verify the green state.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_header_compacts_weather tests\test_frontend_playwright.py::test_frontend_mobile_todo_layout_is_compact_and_tappable -q`

Expected: `4 passed`.

- [ ] **Step 3: Run the full frontend browser suite.**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q`

Expected: all frontend Playwright tests pass.

- [ ] **Step 4: Commit the CSS and regression test.**

Run: `git add static/style.css tests/test_frontend_playwright.py`

Run: `git commit -m "feat: make dashboard responsive on mobile"`

### Task 3: Run project-level verification

**Files:**
- Verify: `static/style.css`
- Verify: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Run the project test script after focused tests are green.**

Run: `.\scripts\test.ps1`

Expected: exit code `0` with no failed tests.

- [ ] **Step 2: Inspect the final scope.**

Run: `git show --stat --oneline HEAD`

Run: `git status --short`

Expected: the feature commit contains `static/style.css` and `tests/test_frontend_playwright.py`; pre-existing user changes remain untouched.
