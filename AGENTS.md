# Canvas Dashboard Agent Guide

Flask webapp for aggregating unfinished assignments and exams from Canvas, 好课, 智学盟, 智慧树, and custom todos.

`AGENTS.md` is the canonical project rule file. `CLAUDE.md` must point to the same content; prefer a symbolic link, and use a hard link on Windows when symbolic-link privilege is unavailable.

## Agent Rules

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
└── CLAUDE.md                      # Symlink to AGENTS.md
```

## Install And Run

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
.\scripts\dev.ps1
```

Development and production both listen on port `5000` by default.

Production entrypoint:

```powershell
python serve.py
```

The Windows wrapper `canvas-server.vbs` starts the production server without a visible console.

## Tests

Preferred local checks:

```powershell
.\scripts\test.ps1
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
.\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

The deploy script runs local tests, packages the app excluding `.venv`, `data`, caches, `.git`, and agent directories, uploads via `scp`, restarts `canvas-dashboard`, and checks systemd status.

Production notes:

- nginx proxies port `80` to `127.0.0.1:5000`; see `deploy/canvas-dashboard.nginx`.
- systemd uses `deploy/canvas-dashboard.service`; `ExecStart` runs `.venv/bin/python serve.py`.
- `/healthz` is public and checks only local app/data/worker state.
- Server-side `data/` is not included in deployments and is independent from local data.
- Do not test open registration on production with throwaway accounts when real legacy data may still exist, because the first registered account can claim legacy top-level data files.

## API Routes

All routes except `/healthz`, `/login`, `/register`, `/api/auth/register`, and `/api/auth/login` require a site account session. Page routes redirect unauthenticated users to `/login`; `/api/*` returns `401 {"ok": false}`.

| Route | Methods | Purpose |
| --- | --- | --- |
| `/healthz` | GET | Public local health check for app, writable data, and Zhihuishu worker status |
| `/login` | GET | Site account login page |
| `/register` | GET | Site account registration page |
| `/api/auth/register` | POST | Register and automatically log in |
| `/api/auth/login` | POST | Site account login |
| `/api/auth/logout` | POST | Clear site session |
| `/` | GET | Main frontend app |
| `/api/clock` | GET | Server date/time |
| `/api/weather` | GET | Shanghai weather via Open-Meteo |
| `/api/term` | GET | Term and week data |
| `/api/term/refresh` | POST | Refresh term data through CDP |
| `/api/config` | GET/POST | Canvas feed URL config |
| `/api/canvas/todos` | GET | Canvas assignments |
| `/api/canvas/state` | GET/POST | Canvas hidden/highlighted/deleted state |
| `/api/haoke/config` | GET/POST | 好课 credential config |
| `/api/haoke/todos` | GET | 好课 assignments |
| `/api/haoke/state` | GET/POST | 好课 state |
| `/api/zhixuemeng/send-sms` | POST | Send 智学盟 SMS code |
| `/api/zhixuemeng/login` | POST | 智学盟 SMS login |
| `/api/zhixuemeng/login-password` | POST | 智学盟 password login |
| `/api/zhixuemeng/logout` | POST | Clear 智学盟 token and assignment cache |
| `/api/zhixuemeng/config` | GET | 智学盟 login/course status |
| `/api/zhixuemeng/course` | POST | Select 智学盟 course |
| `/api/zhixuemeng/todos` | GET | 智学盟 assignments |
| `/api/zhixuemeng/state` | GET/POST | 智学盟 state |
| `/api/custom/todos` | GET/POST | List or create custom todos |
| `/api/custom/todos/<id>` | PUT/DELETE | Update or delete a custom todo |
| `/api/zhihuishu/config` | GET | 智慧树 login/cache status |
| `/api/zhihuishu/todos` | GET | 智慧树 assignments from cache |
| `/api/zhihuishu/state` | GET/POST | 智慧树 state |
| `/api/zhihuishu/login-required` | POST | Mark 智慧树 login required |
| `/api/zhihuishu/login-session` | POST/DELETE | Create or stop the current 智慧树 login window |
| `/api/zhihuishu/login-session-auth` | GET | 智慧树 noVNC reverse-proxy auth |
| `/api/zhihuishu/login-session/<token>/complete` | POST | Complete login window and trigger refresh |
| `/api/zhihuishu/login-session/<token>` | DELETE | Stop a specific login window |
| `/zhihuishu/session/<token>/` | GET | 智慧树 login window landing page |
| `/login/<platform>` | GET | Platform credential page after site login |

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

Per-user files under `data/users/<username>/`:

| File | Purpose |
| --- | --- |
| `custom_todos.json` | Custom todos with `id`, `text`, `done`, `created_at`, `updated_at`, `due_date`, `highlighted`, `labels`, `subtasks` |
| `config.json` | Canvas URL, encrypted 好课 credentials, encrypted 智学盟 token, selected 智学盟 course |
| `canvas_state.json` | Canvas hidden/highlighted/deleted state |
| `haoke_state.json` | 好课 state |
| `zhixuemeng_state.json` | 智学盟 state |
| `zhihuishu_state.json` | 智慧树 state |
| `canvas_cache.json` | Canvas parsed iCal cache |
| `haoke_cache.json` | 好课 assignment cache |
| `zhixuemeng_cache.json` | 智学盟 assignment cache, 30 minute TTL |
| `zhihuishu_status.json` | 智慧树 worker/session status |
| `zhihuishu_cache.json` | 智慧树 assignment cache |
| `zhihuishu_login_session.json` | 智慧树 short login-window metadata |
| `zhihuishu_cookies.json` | Legacy 智慧树 cookie compatibility file |
| `zhihuishu_chromium_profile/` | Per-user 智慧树 Chromium profile |

Global files under `data/`:

| File | Purpose |
| --- | --- |
| `users.json` | Site user registry |
| `.flask_secret_key` | Flask session signing key |
| `.encryption_key` | Fernet key shared by all account credential encryption |
| `holiday_cache.json` | Official holiday cache |
| `term_cache.json` | Term/week cache |
| `term_config.json` | Local fallback term label and start date |
| `zhixuemeng_gaoshu_*.md` | Manual 智学盟 export output |
| `zhixuemeng_gaoshu_*_raw.json` | Manual 智学盟 raw export output |

## Storage And Concurrency

`storage.py` is the central helper for runtime JSON safety:

- Lock keys use normalized absolute paths.
- Writes use a temp file plus atomic replace, with a short Windows retry for transient replace failures.
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

- `renderUnifiedList()` merges Canvas, 好课, 智学盟, 智慧树, and custom todos into one list.
- Custom todo IDs use a `c` prefix on the frontend, for example `c16`.
- 智学盟 IDs use a `zxm_` prefix in the unified list.
- `customItems` stores custom todos in frontend memory.
- User input like `任务名称 #标签1 #标签2` extracts labels from whitespace-separated `#` tokens.
- `saveInlineEdit(..., field='multi')` sends `text` and `labels` together to avoid racing parallel PUTs.
- Custom todo subtasks live in each todo's `subtasks` array as `{id, text, done}`.
- Subtask expanded state is frontend-only in `expandedCustomTodoIds` and resets after refresh.
- External platform rows render a disabled triangle placeholder so dates and right-side action icons stay aligned.

`GET /api/custom/todos` still auto-deletes completed custom todos whose due date is earlier than today. Sorting is unfinished first, then dated items first, then due date ascending. If this sorting changes, check `renderUnifiedList()` at the same time.
