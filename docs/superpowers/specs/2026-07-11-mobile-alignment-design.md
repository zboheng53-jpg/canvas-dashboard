# Mobile layout alignment design

## Goal

Make three phone-only alignment adjustments requested from the deployed compact
layout. Desktop behavior and all todo actions remain unchanged.

## Changes at widths of 768px and below

- Place the subtask expander at the right edge of the label row instead of giving
  it a separate left-aligned row. Labels keep their existing truncation behavior.
- Vertically center the `待办清单` heading within the tall section-header area
  created by the account controls on its right.
- Place the weather emoji and temperature on one horizontal line. Weather detail
  text remains hidden and the term line remains hidden, as in the compact design.

## Implementation boundaries

- Change only the mobile CSS rules in `static/style.css` and their Playwright
  assertions in `tests/test_frontend_playwright.py`.
- Do not change templates, JavaScript, API calls, todo persistence, or desktop CSS.

## Verification

At 375px, 390px, and 768px, Playwright verifies the weather emoji is left of the
temperature on the same row, the section heading is vertically centered against
the header controls, and the subtask expander is positioned to the right of the
labels. At 769px, the existing desktop layout remains unchanged.
