# Architecture

Canvas Dashboard is a single-process Flask/Waitress application that aggregates unfinished work from Canvas, 好课, 智学盟, 智慧树, and user-created todos. Production uses nginx for TLS and reverse proxying, while a separate systemd worker refreshes 智慧树 data.

## Runtime Topology

```text
Browser / Apple Calendar
        |
        v
nginx :80/:443
        |
        +--> Waitress 127.0.0.1:5000
        |      +--> account/session and platform APIs
        |      +--> local JSON data under data/
        |      +--> private token-authenticated ICS feed
        |
        +--> token-gated noVNC login containers
               +--> persistent per-user 智慧树 profile
               +--> ephemeral per-user Tongji profile

zhihuishu-worker.service
        +--> one isolated child process per user refresh
        +--> per-user Chromium profile
        +--> cache/status JSON consumed by Flask
```

The Flask request path never launches a 智慧树 browser. Platform caches let the dashboard keep serving local data when an upstream service is slow or unavailable.

## Main Components

| Component | Responsibility |
| --- | --- |
| `app.py` | Routes, authentication boundary, response aggregation, health check, and ICS item selection |
| `auth.py`, `user_paths.py` | Site accounts, password hashes, persistent session key, and per-user paths |
| `storage.py` | Locked JSON reads/updates, atomic replacement, and fail-closed corruption handling |
| `canvas_auth.py` | Canvas iCalendar validation, fetch, parse, cache, and item state |
| `haoke_client.py` | Encrypted credentials, cache-first assignment fetch, and guarded background refresh |
| `zhixuemeng_client.py` | Token login, course selection, assignment fetch, cache, and logout cleanup |
| `zhihuishu_worker.py` | User discovery, per-user timeout isolation, refresh scheduling, and status updates |
| `zhihuishu_browser.py` | Playwright session checks, keepalive, and assignment extraction |
| `zhihuishu_login_sessions.py` | Short tokenized Docker/noVNC login windows backed by persistent per-user profiles |
| `tongji_login_sessions.py` | Short tokenized Docker/noVNC enhanced-auth windows with ephemeral per-user profiles |
| `apple_calendar.py` | Hashed subscription-token lifecycle and RFC 5545 serialization |
| `tongji_timetable.py`, `schedule_store.py` | Authenticated CDP timetable parsing plus per-user course and schedule-item storage |
| `project_store.py` | Atomic per-user long-term projects and weekly goals |
| `templates/index.html` | Vanilla-JavaScript unified list, responsive dashboard shell, and all dashboard interactions |
| `templates/dashboard/*.html`, `static/dashboard-shell.css` | Isolated sidebar, live right-rail modules, management views, and shell layout styles |

## Accounts And Data Isolation

Site accounts are separate from third-party platform accounts. `data/users.json` stores site password hashes. Each site account owns `data/users/<username>/`, including platform configuration, item state, caches, custom todos, Apple Calendar token hash, and its 智慧树 browser profile.

The first registered account may claim eligible legacy top-level runtime files. Never create a throwaway first production account when legacy data may still exist.

Global secrets and shared settings live under `data/`:

- `.flask_secret_key` signs sessions; replacing it logs everyone out.
- `.encryption_key` decrypts stored platform credentials; it must be restored with `config.json`.
- `term_config.json` provides the local term fallback.

See `AGENTS.md` for the current file contract and `docs/backup-and-restore.md` for protection and recovery.

## JSON Safety And Concurrency

`storage.py` normalizes lock keys to absolute paths and uses a per-path re-entrant lock. Writes go to a temporary file, are flushed with `fsync`, and then atomically replace the destination. Custom-todo read/modify/write operations use `locked_json_update()` so Waitress threads do not lose updates.

Malformed or non-UTF-8 JSON is fail-closed:

1. The original remains untouched.
2. A sibling `.corrupt-<timestamp>` forensic copy is preserved.
3. `JsonFileCorruptionError` stops the operation.
4. Flask returns HTTP 503 for API requests instead of writing an empty default.

These locks are process-local. A future multi-process application deployment must add a cross-process lock or move runtime state to a database.

## Refresh Paths

- Canvas fetches and parses the configured iCalendar feed, then stores a local cache.
- 好课 serves an existing cache immediately; a stale cache starts at most one in-process refresh per user. The first load without a cache remains synchronous.
- 智学盟 caches assignments for 30 minutes and clears both token and cache on logout.
- 智慧树 runs outside Flask. Every all-user round rediscovers account directories. Each user runs in a child process with a 180-second default timeout, so one stuck account does not block later users. Per-user `last_success_at` values are summarized by `/healthz`.

## Custom Todos And Calendar

Custom todos store labels and subtasks in `custom_todos.json`. A subtask has `id`, `text`, `done`, and optional `due_date`; completing all subtasks does not complete the parent.

The private Apple Calendar feed includes:

- unfinished, visible, dated cached platform items;
- unfinished custom parent todos with `due_date`;
- unfinished custom subtasks with their own `due_date`, even when the parent has no date.

Completed parents suppress all their subtasks. Completed or undated subtasks are not exported. Only the SHA-256 hash of a subscription token is persisted, and nginx disables access logging for `/calendar/`.

The dated external-platform-subtask proposal under `docs/superpowers/` is not implemented; imported platform assignments do not currently have locally editable subtasks.

## Dashboard V2 Schedule And Projects

Dashboard V2 keeps the original unified todo and platform flows in the central column. The independent right-rail modules read per-user data through:

- `/api/projects` and `/api/projects/overview` for active/archived projects and weekly goals;
- `/api/schedule`, `/api/schedule/refresh`, and `/api/schedule/today` for courses, recurring items, one-off items, and today's deadlines.

`project_store.py` writes `projects.json`; `schedule_store.py` writes `course_schedule.json` and `schedule_items.json`. All three files live under `data/users/<username>/`, use the shared locked/atomic JSON helpers, and fail closed on corruption. Mutating routes remain behind the site session and global CSRF boundary.

The timetable button creates a short-lived, site-session-bound noVNC browser and opens the Tongji personal-timetable URL directly. The user completes WeChat QR or SMS enhanced authentication inside that window. On confirmation, Flask connects to that container's loopback-only CDP endpoint, waits for the personal timetable, and parses only rendered `table:visible` elements. Browser-side normalization expands `rowspan` and `colspan`; the selected-course list remains authoritative for weekday, periods, weeks, and locations, while the visible timetable grid filters out stale or hidden-term course codes.

The flow never persists a Tongji password. Its temporary profile is removed when the session completes, expires, or is cancelled. A failed or unauthenticated refresh leaves the previous successful course cache untouched. Frontend academic-week calculations use local calendar-day components so every Monday-through-Sunday row maps to the same week. The homepage today endpoint reads existing platform caches for deadlines; it does not issue a second upstream task refresh.

The two right-rail components keep separate DOM, state, rendering functions, and manager views. At desktop width they share the fixed-height rail; narrower layouts move the rail below the central todo column, and mobile stacks the project and schedule cards vertically.

## Production Releases

Production state is split deliberately:

```text
/home/ubuntu/canvas-dashboard/
├── current -> releases/<release-name>
├── releases/             immutable application releases
├── data/                 persistent runtime data
├── .venv/                shared Python environment
├── backups/              encrypted server-side backup copies
└── incoming/             temporary upload area
```

Each release links to the shared `data/` and `.venv/`. Activation atomically switches `current`, installs systemd/nginx configuration, restarts services, and runs local plus HTTPS health checks. A failed activation restores the previous release automatically. After a successful activation, the installer keeps the newest five releases and always protects the active and recorded rollback targets.

Operational commands and rollback procedure are in `docs/operations.md`.
