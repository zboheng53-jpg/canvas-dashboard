# Mobile responsive dashboard design

## Goal

Make the existing Canvas Dashboard URL comfortable to use in a phone browser. The
same Flask pages and client-side behavior remain in place; this work does not add
an installable app, native app, new routes, or new persisted data.

## Chosen layout

At widths of 768px and below, the dashboard uses a compact, single-column layout.
The desktop layout above that breakpoint remains unchanged.

### Header and controls

- Keep the clock, weather, date, and term information visible in a compact header.
- On phones, place the time and date on the left and stack the weather emoji over
  the temperature at the upper right, matching the approved visual reference.
  Hide the weather description and wind/humidity detail at this width; retain them
  on desktop.
- Let the dashboard and card gutters shrink for small screens without removing the
  existing visual hierarchy.
- Let the dashboard heading and account/login controls wrap rather than overflow.
- Make the custom-todo text field occupy its own row on narrow screens; retain the
  date field and add button together on the following row.
- Keep platform-login cards in a two-column grid.

### Todo rows

Each unified todo becomes a compact two-row CSS grid on phone widths:

1. The source badge, title, and due date share the primary row.
2. Labels and controls use the secondary area without competing with the title.

Course text remains hidden on phone widths, matching the current intent to avoid
overcrowding. The source, title, due date, subtask control, highlight, complete/
hide, and delete actions remain available. Mobile action buttons receive a minimum
36px by 36px touch target. Long titles truncate rather than creating horizontal
scrolling.

## Implementation boundaries

- Restrict production changes to responsive CSS in `static/style.css` unless a
  test shows the existing DOM cannot support the layout.
- Do not change Flask routes, API payloads, local storage, or todo behavior.
- Do not change desktop styles outside the responsive breakpoint.
- Preserve existing urgency, dismissed, subtask, and label states in the mobile
  layout.

## Verification

Add Playwright coverage that opens the authenticated dashboard at 375px, 390px,
and 768px widths. The test will verify that the viewport has no horizontal
overflow, the add-todo controls remain usable, a seeded todo's title, due date,
and action controls are visible, and the mobile layout is active at the phone
widths. Existing frontend and full test suites remain passing.

## Explicit non-goals

- PWA manifests, service workers, installation prompts, or a standalone mobile
  application.
- A separate mobile URL or alternate templates.
- Changes to the dashboard's task sorting or platform integrations.
