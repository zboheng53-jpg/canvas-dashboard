# Mobile weather and term information design

## Goal

Restore the secondary weather and term information in the upper-right portion of
the phone header. The compact clock, weather icon, and temperature remain in
their current positions, while the additional information matches the desktop
content as closely as the phone layout allows. Desktop layout and behavior stay
unchanged.

## Phone layout at widths of 768px and below

- Keep the weather icon and temperature on their existing shared top row.
- Show a right-aligned weather-detail line directly below them. It uses the
  existing weather description and weather-detail data, which already contain
  the condition, wind speed, and humidity.
- Show a second right-aligned term line below the weather-detail line. It uses
  the existing full term and week text and retains the existing refresh button.
- Keep both supplemental lines compact and non-wrapping. If an unusually long
  response cannot fit at the narrowest viewport, it is clipped with an ellipsis
  instead of creating an extra header row or horizontal page overflow.
- Preserve a clear visual hierarchy: icon and temperature remain prominent;
  weather detail and term information use smaller secondary text.

## Implementation boundaries

- Change only the mobile CSS overrides in `static/style.css` and the relevant
  Playwright assertions in `tests/test_frontend_playwright.py`.
- Reuse the existing `weather-desc`, `weather-detail`, `term-info`, and
  `refreshTerm()` markup and data flow. No API, JavaScript, template, storage,
  or todo behavior changes are needed.
- Do not change desktop CSS or the desktop header presentation.

## Verification

At 375px, 390px, and 768px, Playwright verifies that:

- the weather icon and temperature share the top row;
- the weather condition/detail is visible on one compact row beneath it;
- the term text and refresh control are visible on the next row; and
- the header has no horizontal overflow.

At 769px, existing desktop weather and term layout assertions remain unchanged.

## Non-goals

- Adding new weather or term API fields.
- Changing the weather update cadence or term refresh behavior.
- Introducing a separate phone template or modifying desktop spacing.
