# Compact mobile dashboard design

## Goal

Reduce the vertical density of the phone dashboard while retaining every existing
todo operation. The desktop layout and the desktop interaction model remain
unchanged.

## Chosen approach

At widths of 768px and below, use a compact mobile interaction model rather than
only shrinking existing controls.

### Header

- Keep the time, date, and weather emoji/temperature visible.
- Hide the long term/semester text on phones; it is secondary information that
  currently consumes a whole visual line.
- Keep the compact weather stack already introduced in the previous responsive
  work.

### Add-todo control

- Keep the existing native date input so users can choose a deadline directly.
- Present the title input, date control, and add control as one horizontal mobile
  toolbar. The date control becomes a compact calendar affordance rather than a
  full-width locale-formatted date field.
- The control remains keyboard- and touch-accessible and keeps the existing
  submission behavior.

### Todo rows and actions

- Retain the source badge, title, due date, labels, and subtask expander in every
  collapsed row.
- Replace the always-visible flag, complete/hide, and delete buttons with a single
  mobile-only `more` button. Selecting it reveals those same existing controls in
  a compact row for that item.
- Only one item action menu may be open at a time. Tapping the same `more` button
  closes its menu; opening another item closes the previous one.
- Desktop keeps the current inline action buttons. No API, storage, todo sorting,
  or state semantics change.

## Implementation boundaries

- Change only `templates/index.html`, `static/style.css`, and the relevant
  Playwright browser tests.
- Reuse the current action handlers (`toggleHighlight`, completion/hide handlers,
  and delete handlers); the mobile menu changes presentation only.
- Do not introduce a third-party UI library or a second mobile template.

## Verification

At 375px, 390px, and 768px viewport widths, Playwright must verify:

- the term line is hidden and the add-todo controls fit one row without horizontal
  overflow;
- collapsed todos do not render the full action row;
- opening `more` exposes the existing action buttons for that item and closes any
  other open menu;
- the title, due date, labels, and subtask expander remain visible; and
- desktop action controls remain present at a desktop viewport.

## Non-goals

- Swipe gestures, PWA behavior, or separate mobile routes.
- Changing how deadlines, labels, subtasks, or external-platform states are
  persisted.
