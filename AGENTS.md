# Canvas Dashboard Agent Guide

Flask webapp for aggregating unfinished assignments and exams from Canvas, 好课, 智学盟, 智慧树, and custom todos.

`AGENTS.md` is the canonical project rule file. `CLAUDE.md` must point to the same content; prefer a symbolic link, and use a hard link on Windows when symbolic-link privilege is unavailable.

## Agent Rules

- 每次面对一个新问题的时候，先新建一个 Git 分支，然后再对代码完成修改和检验通过之后，部署到服务器上。
- Read the relevant code and existing patterns before editing. Prefer `rg` / `rg --files` for search.
- Make the smallest change that satisfies the request. Do not refactor unrelated code or reformat whole files.
- Do not overwrite, delete, or migrate user data unless explicitly requested. Treat `data/`, platform credentials, caches, and production config as sensitive.
- For auth, encryption keys, migrations, file writes, and deployment changes, write or run matching verification before claiming success.
- Report facts plainly. If a command cannot be run, say why.
- Core language focus is Python, with simple direct code preferred over unnecessary abstraction.

## Project Layout

```text
canvas-dashboard/
├── app.py                         # Flask routes and API handlers
├── auth.py                        # Site account system, password hashing, legacy migration
├── user_paths.py                  # Per-user data paths under data/users/<username>/
├── storage.py                     # Locked JSON reads/writes and atomic replace
├── tongji_timetable.py             # 一网通办课表 CDP fetch and parser
├── schedule_store.py               # Per-user course and schedule-item storage
├── project_store.py                # Per-user long-term project storage
├── canvas_auth.py                 # Canvas iCal fetching and parsing
├── haoke_client.py                # 好课 client and cache handling
├── zhixuemeng_client.py           # 智学盟 client, token, course, assignment APIs
├── zhihuishu_store.py             # 智慧树 cache/status/state storage
├── zhihuishu_worker.py            # 智慧树 background worker
├── zhihuishu_browser.py           # 智慧树 Playwright browser automation
├── zhihuishu_login_sessions.py    # 智慧树 short noVNC login windows
├── fetch_haoke_raw.py             # 好课 raw data fetch helper
├── generate_markdown_v4.py        # 好课 raw JSON to Markdown helper
├── requirements.txt               # Python dependencies
├── templates/index.html           # Vanilla JS frontend app
├── templates/auth_*.html          # Site login/register pages
├── templates/login_*.html         # Platform credential pages
├── static/style.css               # Styles
├── tests/                         # unittest/pytest and Playwright regression tests
├── deploy/                        # nginx and systemd reference configs
├── data/                          # Local runtime data, never casually modify
├── AGENTS.md                      # Canonical agent guide
└── CLAUDE.md                      # Same content as AGENTS.md (hard link on Windows)
```

## Install And Run

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
.\local-preview.bat
```

Use `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1`
when the server needs to stay in the foreground for diagnostics.

Local development and Waitress both listen on `127.0.0.1:5000` by default. `serve.py` is the production entrypoint; systemd runs it from `/home/ubuntu/canvas-dashboard/current`.

## Tests

Preferred local checks:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

Targeted examples:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q
```

Scale verification to the risk of the change. For route, auth, storage, or frontend behavior changes, run the relevant targeted tests plus the full suite when feasible.

## Production Deployment

Production server: `ubuntu@124.222.188.101:/home/ubuntu/canvas-dashboard`

Deploy through the project skill script after local verification:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

The deploy script runs the full test/compile gates, creates and restores an encrypted off-server backup in an isolated drill, uploads an immutable release through the pinned `deploy/known_hosts`, atomically switches `current`, and automatically restores the previous release on activation or health failure.

Production notes:

- nginx redirects HTTP to HTTPS and terminates TLS on `canvas-dashboard.xyz`; see `deploy/canvas-dashboard.https.nginx`.
- systemd units use `/home/ubuntu/canvas-dashboard/current`; shared runtime state remains at the project root.
- `/healthz` is public, checks only local app/data/worker state, and summarizes 智慧树 `last_success_at` values without refreshing.
- Server-side `data/` is not included in deployments and is independent from local data.
- Do not test open registration on production with throwaway accounts when real legacy data may still exist, because the first registered account can claim legacy top-level data files.
- Full deployment, rollback, service, certificate, and incident commands are in `docs/operations.md`.

## API Routes

All routes except `/healthz`, `/login`, `/register`, `/api/auth/register`, `/api/auth/login`, and token-authenticated `/calendar/<token>.ics` require a site account session. Page routes redirect unauthenticated users to `/login`; `/api/*` returns `401 {"ok": false}`. CSRF protection applies to every POST/PUT/PATCH/DELETE request.

Route groups:

- `/api/auth/*`: register, login, and logout.
- `/api/{canvas,haoke,zhixuemeng,zhihuishu}/*`: platform configuration, todos, state, and login actions.
- `/api/custom/todos[/<id>]`: custom-todo CRUD.
- `/api/apple-calendar/subscription` and `/calendar/<token>.ics`: private subscription lifecycle and feed.
- `/api/schedule`: course cache, CDP refresh, recurring/one-off item CRUD, and today's busy schedule.
- `/api/projects`: long-term project, weekly-goal, archive, and overview APIs.
- `/api/term`, `/api/term/refresh`, `/api/clock`, and `/api/weather`: dashboard context.
- `/api/zhihuishu/login-session*` and `/zhihuishu/session/<token>/`: token-gated login windows.

When routes change, verify the actual `app.url_map`, authentication exemption set, CSRF boundary, and route tests together.

## Site Accounts And User Data

The site account system lives in `auth.py` and `user_paths.py`.

- Registration is intentionally open: anyone with access to the site can create an account.
- Passwords are hashed with Werkzeug and stored in `data/users.json`.
- Flask session signing key is persisted in `data/.flask_secret_key`. Deleting it logs everyone out.
- Login sessions are long-lived by design: `app.permanent_session_lifetime` is 3650 days.
- Each account stores platform data under `data/users/<username>/`.
- Global files shared by all accounts are `data/users.json`, `data/.flask_secret_key`, `data/.encryption_key`, `data/holiday_cache.json`, and `data/term_cache.json`.

Legacy migration:

- Before the multi-user system, runtime files were top-level under `data/`.
- The first registered account automatically claims eligible legacy files into its own user directory.
- Later accounts start with empty dashboards.
- Never casually register a temporary first account on a production instance that may contain real top-level data.

Platform credential pages are separate from site account login:

- `/login` and `/register` decide who the site user is.
- `/login/canvas`, `/login/haoke`, `/login/zhixuemeng`, and `/login/zhihuishu` configure that user's third-party platform credentials.

## Data Files

Per-user durable files include `custom_todos.json`, `apple_calendar.json`, `course_schedule.json`, `schedule_items.json`, `projects.json`, `config.json`, and the four `*_state.json` files. Per-user caches/status/login metadata and `zhihuishu_chromium_profile/` are runtime artifacts. Global durable files include `users.json`, `.flask_secret_key`, `.encryption_key`, and optional `term_config.json`; holiday and term caches are rebuildable.

`custom_todos.json` stores `id`, `text`, `done`, timestamps, optional parent `due_date`, `highlighted`, `labels`, and `subtasks`. Each subtask stores `id`, `text`, `done`, and optional `due_date`.

The exact data flow and backup inclusion policy are documented in `docs/architecture.md` and `docs/backup-and-restore.md`.

## Storage And Concurrency

`storage.py` is the central helper for runtime JSON safety:

- Lock keys use normalized absolute paths.
- Writes use a temp file plus atomic replace, with a short Windows retry for transient replace failures.
- Malformed or non-UTF-8 JSON is fail-closed: `read_json_file()` preserves the original plus a `.corrupt-<timestamp>` copy and raises `JsonFileCorruptionError`; do not catch that error and write a default value back.
- Custom todo writes for the same account must use `locked_json_update()` to avoid lost updates under Waitress single-process multi-thread serving.
- If deployment ever changes to multiple worker processes, upgrade to a cross-process file lock or a database.

External platform state files all share this shape:

```json
{"hidden": [], "highlighted": [], "deleted": []}
```

Canvas and 好课 item IDs are usually treated as integers. 智学盟 and 智慧树 item IDs are usually strings. Keep types consistent when updating state.

## Platform Notes

### Canvas

- Canvas todos come from the configured iCal feed.
- Parsed results are cached in `canvas_cache.json`.
- Deleted/hidden/highlighted state lives in `canvas_state.json`.

### 好课

- 好课 credentials are stored per site account and encrypted with Fernet.
- Assignment API responses are cached in `haoke_cache.json`.
- `/api/haoke/todos` is cache-first when credentials and a cache file exist; stale cache responses start a guarded in-process daemon refresh, while first load without cache still fetches synchronously.
- Date parsing and cache behavior are covered by tests; keep new behavior deterministic.

### 智学盟

- Uses `X-Access-Token`; token is obtained through SMS or password login and stored encrypted in the user's `config.json`.
- JWT payload `username` is 智学盟's own user name and is distinct from the site account name.
- Course list endpoint: `GET /edu/eduCourseUser/list?pageSize=10000`.
- Todo endpoint: `GET /edu/eduCourseWork/todoList?courseCode=XXX&workCls=10`.
- Full assignment list endpoint: `GET /edu/eduCourseWork/list`.
- Assignment detail endpoint: `GET /edu/eduCourseWork/list?id=WORK_ID`.
- Question list endpoint: `GET /edu/eduCourseWorkTi/list?workId=XXX&pageSize=10000`.
- User answer endpoint: `GET /edu/eduCourseWorkTiUser/list?workId=XXX&userId=XXX`.
- Logout must clear both the persisted token and `zhixuemeng_cache.json`.

### 智慧树

- Flask routes never launch a browser directly. `/api/zhihuishu/todos` only reads cache/status/state.
- Background refresh runs through `zhihuishu_worker.py --all-users`.
- Every round rediscovers users. Each user runs in a timeout-isolated child process, so one stuck account cannot block later accounts.
- Each site account has an isolated Chromium profile under `data/users/<username>/zhihuishu_chromium_profile/`.
- Login or slider failures are handled through short-lived Docker/noVNC login windows guarded by tokens.
- Deployment needs Playwright Chromium installed for the worker: `.venv/bin/python -m playwright install chromium`.
- The reusable long-session browser pattern is documented in `docs/zhihuishu-reusable-web-patterns.md`.

## Term And Holiday Data

`/api/term` uses a two-channel strategy:

1. Prefer CDP scraping through local `localhost:3456` against `https://1.tongji.edu.cn/schoolCalendars`, then persist to `data/term_cache.json`.
2. Fall back to local calculation using `data/term_config.json`, then settings defaults/env overrides.

Holiday detection uses the Tongji workbench API through CDP and caches to `data/holiday_cache.json` for 24 hours. If CDP is unavailable, holidays are simply not shown.

## Frontend Notes

The main app is `templates/index.html`: vanilla JS plus Fetch API.

- The responsive desktop shell is split across `templates/dashboard/*.html` and `static/dashboard-shell.css`; keep new sidebar or right-rail work inside those boundaries when possible.
- On desktop the overview's todo card fills the remaining viewport height below the context card; do not apply that fixed-height behavior to the narrow or mobile layouts.
- The left console navigation is grouped by user intent: `工作区` contains `今日总览`; `计划` contains `长期项目` and `日程与课表`; `管理` contains `连接与同步`, optional `Apple Calendar`, and `偏好设置`. Keep these stable hubs instead of adding one top-level item per platform or action.
- Platform connection cards belong only to the `连接与同步` view. The overview may summarize synchronized tasks but must not duplicate platform account controls.
- Apple Calendar is an optional dedicated dashboard view, not a modal or account-menu action. Keep its navigation item and view behind `APPLE_CALENDAR_ENABLED`.

- `renderUnifiedList()` merges Canvas, 好课, 智学盟, 智慧树, and custom todos into one list.
- Custom todo IDs use a `c` prefix on the frontend, for example `c16`.
- 智学盟 IDs use a `zxm_` prefix in the unified list.
- `customItems` stores custom todos in frontend memory.
- User input like `任务名称 #标签1 #标签2` extracts labels from whitespace-separated `#` tokens.
- `saveInlineEdit(..., field='multi')` sends `text` and `labels` together to avoid racing parallel PUTs.
- Custom todo subtasks live in each todo's `subtasks` array as `{id, text, done, due_date?}`.
- Subtask expanded state is frontend-only in `expandedCustomTodoIds` and resets after refresh.
- External platform rows render a disabled triangle placeholder so dates and right-side action icons stay aligned.
- Apple Calendar exports an unfinished dated subtask independently of the parent's date; a completed parent suppresses all of its subtasks.
- `templates/dashboard/_today_schedule.html` and `_long_term_projects.html` own the two right-rail modules; their managers remain isolated in the `schedule` and `projects` views.

`GET /api/custom/todos` still auto-deletes completed custom todos whose due date is earlier than today. Sorting is unfinished first, then dated items first, then due date ascending. If this sorting changes, check `renderUnifiedList()` at the same time.
