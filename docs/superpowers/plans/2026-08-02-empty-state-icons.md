# Empty State Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tailored low-brightness blue wireframe empty state icons for Todos, Long-term Projects, and Today's Schedule to fill empty dashboard space gracefully.

**Architecture:** Update CSS in `design-system.css` to allow `.ui-empty__art` SVG rendering, and inject custom SVG illustrations matching Style 1 into `index.html`, `projects.js`, and `_placeholder_views.html`.

**Tech Stack:** Vanilla CSS, HTML5 inline SVG, Flask Jinja2 templates, Vanilla JS.

---

### Task 1: CSS Updates for Empty State Icons Display

**Files:**
- Modify: `frontend/assets/css/design-system.css`
- Test: `tests/test_design_system_lint.py`

- [ ] **Step 1: Write a failing lint test for empty state CSS**

Add a test case in `tests/test_design_system_lint.py` checking that `.todo-list .ui-empty__art` and `.rail-card .ui-empty__art` are no longer hidden with `display: none`.

```python
def test_empty_art_not_hidden(design_system_css_content):
    assert ".todo-list .ui-empty__art,\n.rail-card .ui-empty__art { display: none !important; }" not in design_system_css_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_design_system_lint.py -k "test_empty_art_not_hidden" -q`  
Expected: FAIL

- [ ] **Step 3: Modify `design-system.css` to remove display:none and style `.ui-empty__art`**

In `frontend/assets/css/design-system.css`:
Replace lines 1285-1286:
```css
.todo-list .ui-empty__art,
.rail-card .ui-empty__art { display: flex !important; align-items: center; justify-content: center; width: 72px; height: 64px; margin-bottom: 8px; border: none; }
```
And in `frontend/assets/css/components.css` / `design-system.css` ensure `.ui-empty__art` has no default square border when SVG is present.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_design_system_lint.py -q`  
Expected: PASS

- [ ] **Step 5: Commit CSS changes**

```bash
git add frontend/assets/css/design-system.css tests/test_design_system_lint.py
git commit -m "style: enable ui-empty__art SVG rendering in todo list and rail cards"
```

---

### Task 2: Inject Custom SVG for Todos Empty State

**Files:**
- Modify: `frontend/templates/index.html`
- Test: `tests/test_p0_safety.py`

- [ ] **Step 1: Update empty state rendering in `frontend/templates/index.html`**

In `frontend/templates/index.html` around line 1803:
Replace:
```html
          <div class="ui-empty empty-state">
            <span class="ui-empty__art" aria-hidden="true"></span>
            <strong>${unified.length ? '该来源暂无待办事项' : '没有待办事项'}</strong>
            <p>${unified.length ? '切换来源或清除筛选后可查看其他待办。' : '新的课程任务同步后会显示在这里。'}</p>
          </div>
```
With:
```html
          <div class="ui-empty empty-state">
            <span class="ui-empty__art" aria-hidden="true">
              <svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
                <rect x="18" y="14" width="36" height="36" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
                <rect x="24" y="22" width="8" height="8" rx="2" stroke="#3B82F6" stroke-width="1.5" fill="#FFFFFF"/>
                <path d="M26 26L28 28L30 25" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/>
                <rect x="36" y="25" width="12" height="3" rx="1.5" fill="#60A5FA"/>
                <rect x="24" y="36" width="20" height="3" rx="1.5" fill="#BFDBFE"/>
                <path d="M54 14L55 17L58 18L55 19L54 22L53 19L50 18L53 17L54 14Z" fill="#3B82F6"/>
              </svg>
            </span>
            <strong>${unified.length ? '该来源暂无待办事项' : '没有待办事项'}</strong>
            <p>${unified.length ? '切换来源或清除筛选后可查看其他待办。' : '新的课程任务同步后会显示在这里。'}</p>
          </div>
```

- [ ] **Step 2: Run pytest safety tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_p0_safety.py -q`  
Expected: PASS

- [ ] **Step 3: Commit Todos empty state changes**

```bash
git add frontend/templates/index.html
git commit -m "feat(ui): add tailored SVG icon for todos empty state"
```

---

### Task 3: Inject Custom SVG for Long-term Projects Empty State

**Files:**
- Modify: `frontend/assets/js/projects.js`
- Modify: `frontend/templates/dashboard/_placeholder_views.html`
- Test: `tests/test_p0_safety.py`

- [ ] **Step 1: Update empty state rendering in `frontend/assets/js/projects.js` & `_placeholder_views.html`**

Inject Long-term Projects SVG into `.ui-empty__art`:
```html
<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
  <rect x="18" y="18" width="36" height="30" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
  <path d="M26 33H46" stroke="#BFDBFE" stroke-width="1.5"/>
  <circle cx="26" cy="33" r="3" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/>
  <circle cx="36" cy="33" r="3" fill="#FFFFFF" stroke="#3B82F6" stroke-width="1.5"/>
  <circle cx="46" cy="33" r="3" fill="#FFFFFF" stroke="#60A5FA" stroke-width="1.5"/>
  <path d="M22 18V15C22 13.8954 22.8954 13 24 13H30C31.1046 13 32 13.8954 32 15V18" stroke="#93C5FD" stroke-width="1.5"/>
  <path d="M52 14L52.7 16.3L55 17L52.7 17.7L52 20L51.3 17.7L49 17L51.3 16.3L52 14Z" fill="#60A5FA"/>
</svg>
```

- [ ] **Step 2: Run pytest safety tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_p0_safety.py -q`  
Expected: PASS

- [ ] **Step 3: Commit Projects empty state changes**

```bash
git add frontend/assets/js/projects.js frontend/templates/dashboard/_placeholder_views.html
git commit -m "feat(ui): add tailored SVG icon for long-term projects empty state"
```

---

### Task 4: Inject Custom SVG for Today's Schedule Empty State

**Files:**
- Modify: `frontend/templates/index.html`
- Modify: `frontend/assets/js/projects.js`
- Test: `tests/test_p0_safety.py`

- [ ] **Step 1: Update empty state rendering for Today's Schedule**

Inject Schedule SVG into `.ui-empty__art`:
```html
<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
  <rect x="20" y="16" width="32" height="34" rx="5" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
  <path d="M20 23H52" stroke="#BFDBFE" stroke-width="1.5"/>
  <line x1="28" y1="13" x2="28" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="44" y1="13" x2="44" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="36" cy="35" r="7" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/>
  <path d="M36 31V35L39 37" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M52 38L52.7 40.3L55 41L52.7 41.7L52 44L51.3 41.7L49 41L51.3 40.3L52 38Z" fill="#3B82F6"/>
</svg>
```

- [ ] **Step 2: Run all automated tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ -q`  
Expected: All tests pass cleanly

- [ ] **Step 3: Commit Schedule empty state changes**

```bash
git add frontend/templates/index.html frontend/assets/js/projects.js
git commit -m "feat(ui): add tailored SVG icon for today's schedule empty state"
```

---

### Task 5: Final Local Verification & User Acceptance Check

- [ ] **Step 1: Run full Pytest suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`  
Expected: PASS

- [ ] **Step 2: Request user verification on local server**

Per `AGENTS.md` rules: Ask user to verify visual results on http://127.0.0.1:5000/.
