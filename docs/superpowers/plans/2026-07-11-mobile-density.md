# Compact Mobile Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove wasted vertical space from the phone dashboard while retaining every todo action behind an on-demand menu.

**Architecture:** Keep all todo API handlers unchanged. The renderer emits desktop actions plus a mobile-only `more` trigger and menu; CSS selects the appropriate presentation at the mobile breakpoint. A single frontend variable tracks the currently open mobile menu.

**Tech Stack:** Vanilla JavaScript, CSS, pytest, Playwright Python.

---

## File structure

- Modify: `templates/index.html` — mobile action-menu state, trigger, and rendered menu markup.
- Modify: `static/style.css` — compact phone header, calendar-only date control, and action-menu layout.
- Modify: `tests/test_frontend_playwright.py` — mobile density regression coverage and desktop guard.

### Task 1: Write failing compact-mobile behavior tests

**Files:**
- Modify: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Add the failing test below the existing mobile tests.**

```python
@pytest.mark.parametrize("width", [375, 390, 768])
def test_frontend_mobile_compact_controls_and_action_menu(live_app, browser, width):
    page = browser.new_page(viewport={"width": width, "height": 844})
    register_dashboard_user(page, live_app, f"compact{width}")

    expect(page.locator(".term-info")).to_be_hidden()
    form_box = page.locator("#add-todo-form").bounding_box()
    title_box = page.locator("#new-todo-input").bounding_box()
    date_box = page.locator("#new-todo-due").bounding_box()
    add_box = page.locator("#add-todo-form button").bounding_box()
    assert form_box is not None
    assert title_box is not None
    assert date_box is not None
    assert add_box is not None
    assert abs(title_box["y"] - date_box["y"]) < 1
    assert abs(title_box["y"] - add_box["y"]) < 1
    assert page.evaluate("document.documentElement.scrollWidth") <= width

    items = page.locator(".unified-item")
    expect(items).to_have_count(1)
    trigger = items.locator(".mobile-action-trigger")
    expect(trigger).to_be_visible()
    expect(items.locator(".item-mobile-actions")).to_be_hidden()
    expect(items.locator(".item-desktop-actions")).to_be_hidden()

    trigger.click()
    expect(items.locator(".item-mobile-actions")).to_be_visible()
    expect(items.locator(".item-mobile-actions .btn-flag")).to_be_visible()
    expect(items.locator(".item-mobile-actions .btn-dismiss")).to_be_visible()
    expect(items.locator(".item-mobile-actions .btn-delete")).to_be_visible()
```

- [ ] **Step 2: Add a desktop guard test.**

```python
def test_frontend_desktop_keeps_inline_todo_actions(live_app, browser):
    page = browser.new_page(viewport={"width": 1024, "height": 844})
    register_dashboard_user(page, live_app, "desktopactions")

    todo = page.locator(".unified-item")
    expect(todo.locator(".item-desktop-actions")).to_be_visible()
    expect(todo.locator(".mobile-action-trigger")).to_be_hidden()
    expect(todo.locator(".item-mobile-actions")).to_be_hidden()
```

- [ ] **Step 3: Run both tests and confirm the red state.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_compact_controls_and_action_menu tests\test_frontend_playwright.py::test_frontend_desktop_keeps_inline_todo_actions -q`

Expected: failures because the term information is visible, form controls wrap, and no mobile action trigger exists.

### Task 2: Render mobile-only action menus

**Files:**
- Modify: `templates/index.html:440-570`
- Test: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Add this state and toggle helper near the other frontend render state.**

```javascript
let openMobileActionItemId = null;

function toggleMobileActions(itemId) {
  openMobileActionItemId = openMobileActionItemId === itemId ? null : itemId;
  renderUnifiedList();
}
```

- [ ] **Step 2: In `renderUnifiedList()`, replace the final action spans in `rowHtml` with this markup.**

```javascript
const mobileActionsOpen = openMobileActionItemId === item.id;
const mobileActionsHtml = actionsHtml
  ? `<button class="mobile-action-trigger" onclick="toggleMobileActions('${item.id}')" aria-label="更多操作" aria-expanded="${mobileActionsOpen}">•••</button>
     <span class="item-mobile-actions ${mobileActionsOpen ? 'open' : ''}">${actionsHtml}</span>`
  : '';

// In rowHtml, replace the existing item-actions span with:
<span class="item-desktop-actions">${actionsHtml}</span>
${mobileActionsHtml}
```

- [ ] **Step 3: Run the two new tests and confirm they remain red until the CSS task.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_compact_controls_and_action_menu tests\test_frontend_playwright.py::test_frontend_desktop_keeps_inline_todo_actions -q`

Expected: mobile test still fails on phone layout; desktop guard passes once the renderer markup exists.

### Task 3: Apply compact phone CSS and verify

**Files:**
- Modify: `static/style.css:1079-1125`
- Test: `tests/test_frontend_playwright.py`

- [ ] **Step 1: Add the following rules inside the existing `@media (max-width: 768px)` block.**

```css
.clock-section .time { font-size: 38px; }
.term-info { display: none; }
.add-todo-form { display: flex; align-items: center; flex-wrap: nowrap; }
.add-todo-form #new-todo-input { flex: 1; min-width: 0; }
.add-todo-form .date-input {
  width: 44px;
  min-width: 44px;
  padding: 0;
  color: transparent;
  font-size: 0;
}
.add-todo-form .date-input::-webkit-datetime-edit { display: none; }
.add-todo-form .date-input::-webkit-calendar-picker-indicator {
  width: 20px;
  height: 20px;
  margin: 0 auto;
  opacity: 0.7;
}
.add-todo-form button { width: 44px; }
.unified-item {
  grid-template-columns: auto minmax(0, 1fr) 36px;
  grid-template-areas:
    "source title more"
    "source due more"
    "source labels labels"
    "source subtask ."
    "source mobile-actions mobile-actions";
}
.item-desktop-actions { display: none; }
.mobile-action-trigger {
  grid-area: more;
  width: 36px;
  height: 36px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-weight: 700;
  letter-spacing: 1px;
}
.item-mobile-actions { display: none; grid-area: mobile-actions; justify-content: flex-end; }
.item-mobile-actions.open { display: flex; }
```

- [ ] **Step 2: Add desktop defaults immediately before the responsive block.**

```css
.item-desktop-actions,
.item-mobile-actions {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
}

.mobile-action-trigger { display: none; }
.item-mobile-actions { display: none; }
```

- [ ] **Step 3: Run focused tests and verify green.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q`

Expected: all frontend browser tests pass.

- [ ] **Step 4: Run full verification and commit.**

Run: `C:\DesktopFiles\canvas-dashboard\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

Run: `git add templates/index.html static/style.css tests/test_frontend_playwright.py`

Run: `git commit -m "feat: compact mobile todo controls"`
