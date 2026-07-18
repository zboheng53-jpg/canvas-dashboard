# Mobile Weather and Term Information Implementation Plan

> Historical planning record. The current phone header behavior is defined by `static/style.css` and the Playwright regression suite, not by this unchecked implementation checklist.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show compact weather details and term information beneath the current weather icon and temperature in the mobile dashboard header without changing desktop presentation.

**Architecture:** The existing header markup and API-populated elements already contain all required data. Update only the `max-width: 768px` CSS overrides so these elements become a two-line right-aligned detail stack, and make the Playwright regression tests verify its visibility, order, and no-overflow constraint.

**Tech Stack:** Flask-rendered HTML, vanilla CSS, pytest, Playwright.

---

## File structure

- Modify: `static/style.css` — replace the phone-only hidden weather-detail and term rules with compact, non-wrapping, right-aligned layout rules. Desktop selectors outside the media query remain untouched.
- Modify: `tests/test_frontend_playwright.py` — update the existing compact-mobile header test and add a desktop guard assertion.

### Task 1: Create the mobile header regression test

**Files:**
- Modify: `tests/test_frontend_playwright.py:142-169`

- [ ] **Step 1: Replace the old hidden-content assertions with a failing mobile regression test**

  Replace `test_frontend_mobile_header_compacts_weather` with this parametrized test:

  ```python
  @pytest.mark.parametrize("width", [375, 390, 768])
  def test_frontend_mobile_header_shows_compact_weather_and_term(live_app, browser, width):
      page = browser.new_page(viewport={"width": width, "height": 844})
      register_dashboard_user(page, live_app, f"mobileheader{width}")

      weather_desc = page.locator(".weather-desc")
      weather_detail = page.locator(".weather-detail")
      term_info = page.locator("#term-info")
      term_refresh = page.locator(".term-refresh-btn")
      expect(weather_desc).to_be_visible()
      expect(weather_detail).to_be_visible()
      expect(weather_detail).to_contain_text("55%")
      expect(weather_detail).to_contain_text("8")
      expect(term_info).to_be_visible()
      expect(term_refresh).to_be_visible()

      emoji_box = page.locator(".weather-emoji").bounding_box()
      temp_box = page.locator(".weather-temp").bounding_box()
      desc_box = weather_desc.bounding_box()
      detail_box = weather_detail.bounding_box()
      term_box = term_info.bounding_box()
      assert all(box is not None for box in (emoji_box, temp_box, desc_box, detail_box, term_box))
      assert emoji_box["x"] < temp_box["x"]
      assert abs((emoji_box["y"] + emoji_box["height"] / 2) - (temp_box["y"] + temp_box["height"] / 2)) <= 2
      assert desc_box["y"] > temp_box["y"]
      assert abs((desc_box["y"] + desc_box["height"] / 2) - (detail_box["y"] + detail_box["height"] / 2)) <= 2
      assert term_box["y"] > desc_box["y"]
      assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
  ```

- [ ] **Step 2: Run the focused test to verify the current CSS fails**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_header_shows_compact_weather_and_term -q
  ```

  Expected: FAIL because `.weather-desc`, `.weather-detail`, and `#term-info` are hidden inside the mobile media query.

- [ ] **Step 3: Add an explicit desktop guard test**

  Add this test directly below the mobile regression test:

  ```python
  def test_frontend_desktop_header_keeps_weather_and_term_layout(live_app, browser):
      page = browser.new_page(viewport={"width": 769, "height": 844})
      register_dashboard_user(page, live_app, "desktopheader")

      expect(page.locator(".weather-desc")).to_be_visible()
      expect(page.locator(".weather-detail")).to_be_visible()
      expect(page.locator("#term-info")).to_be_visible()
      assert page.locator(".weather-card").evaluate(
          "element => getComputedStyle(element).flexDirection"
      ) == "row"
  ```

- [ ] **Step 4: Run the desktop guard before implementation**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_desktop_header_keeps_weather_and_term_layout -q
  ```

  Expected: PASS, proving desktop already has the required presentation.

### Task 2: Implement the phone-only detail stack

**Files:**
- Modify: `static/style.css:1095-1105`
- Test: `tests/test_frontend_playwright.py:142-169`

- [ ] **Step 1: Replace the two hidden mobile rules with compact visible rules**

  Inside the existing `@media (max-width: 768px)` block, replace:

  ```css
  .weather-right { display: none; }
  .term-info { display: none; }
  ```

  with these mobile-only declarations, keeping the existing icon-and-temperature rules unchanged:

  ```css
  .top-right-group { min-width: 0; max-width: 52%; }
  .weather-card { min-width: 0; gap: 4px; }
  .weather-right {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    min-width: 0;
    max-width: 100%;
  }
  .weather-desc,
  .weather-detail,
  .term-info #term-info {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .weather-desc { font-size: 11px; }
  .weather-detail { font-size: 10px; }
  .term-info {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    min-width: 0;
    max-width: 100%;
    font-size: 10px;
    text-align: right;
  }
  .term-info #term-info { min-width: 0; }
  .term-refresh-btn { flex: 0 0 auto; }
  ```

  If the focused test shows that 52% still causes a horizontal scrollbar at a
  supported viewport, reduce only that percentage to the smallest value that
  eliminates overflow while keeping the weather icon and temperature on their
  shared row.

- [ ] **Step 2: Run the new mobile regression test**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_mobile_header_shows_compact_weather_and_term -q
  ```

  Expected: PASS for all three mobile widths.

- [ ] **Step 3: Run the desktop guard again**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py::test_frontend_desktop_header_keeps_weather_and_term_layout -q
  ```

  Expected: PASS, confirming the media-query-only change did not alter the desktop header.

- [ ] **Step 4: Commit the implementation and regression tests**

  Run:

  ```powershell
  git add static/style.css tests/test_frontend_playwright.py
  git commit -m "feat: restore mobile weather details"
  ```

### Task 3: Run the complete frontend verification suite

**Files:**
- Test: `tests/test_frontend_playwright.py`
- Test: `tests/test_frontend_text_integrity.py`

- [ ] **Step 1: Run all Playwright frontend tests**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q
  ```

  Expected: PASS with the new mobile header assertions and all existing todo interaction tests.

- [ ] **Step 2: Run the frontend text-integrity test**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_frontend_text_integrity.py -q
  ```

  Expected: PASS; no template text or encoding-sensitive markup changed.

- [ ] **Step 3: Run the project test script**

  Run:

  ```powershell
  .\scripts\test.ps1
  ```

  Expected: PASS with no failures.
