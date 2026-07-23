# Canvas Dashboard

Flask web app for a personal Tongji University dashboard. It aggregates unfinished work from Canvas, Haoke, Zhixuemeng, Zhihuishu, and manual todos, with a per-user course schedule and lightweight long-term projects.

Production is live at [https://canvas-dashboard.xyz](https://canvas-dashboard.xyz) with ICP filing, HTTPS, secure session cookies, and private Apple Calendar subscriptions enabled.

## Documentation

- `docs/architecture.md`: runtime components, data flow, storage safety, worker isolation, and release topology.
- `docs/operations.md`: deployment, rollback, services, health checks, HTTPS, and incident commands.
- `docs/backup-and-restore.md`: encrypted backup ownership, automation, recovery drills, and staged restoration.
- `docs/README.md`: current-versus-historical documentation index.
- `deploy/zhihuishu-login-tunnel.md`: 智慧树 login-window and worker operations.
- `AGENTS.md`: concise implementation rules and current code contracts for coding agents.

## Install

Use the project virtual environment. The helper scripts intentionally fail if `.venv` is missing so tests and local runs do not fall back to a global Python.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```

Linux production hosts use the same package list:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

## Run

Windows development:

```powershell
.\scripts\dev.ps1
```

Direct entry points:

```powershell
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe serve.py
```

The app listens on `127.0.0.1:5000` by default. Override with `CANVAS_DASHBOARD_HOST` and `CANVAS_DASHBOARD_PORT`.

## Test

```powershell
.\scripts\test.ps1
.\scripts\test.ps1 tests\test_healthz.py -q
```

The script pins `.venv`, sets UTF-8 output, checks required Python packages, and then runs `pytest`.

## Tongji Timetable

Open **日程与课表** and click **统一身份认证登录**. A short-lived browser window opens directly; complete WeChat QR or SMS enhanced authentication there and wait for the personal timetable to appear. Return to the dashboard and click **我已完成认证，导入课表**.

The server reads only the currently rendered timetable tables from that isolated browser session. It does not store the Tongji password or retain the temporary browser profile after completion or expiry. A failed refresh leaves the last successful course cache untouched. The Excel extension remains available as a manual fallback.

## Apple Calendar

After signing in to the production dashboard, open **日历订阅** from the bottom of the sidebar. The panel can generate and copy the private HTTPS feed URL or revoke it. Treat the URL like a password: anyone holding it can read that account's exported task titles and dates.

The feed includes unfinished, visible, dated platform items; dated unfinished custom todos; and unfinished custom subtasks that have their own `due_date`. A dated subtask is exported even if its parent has no date. Completed parents, completed subtasks, and undated subtasks are excluded.

## Deploy

Run the verified release workflow from Windows:

```powershell
.\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

It runs the full test and compile gates, performs an encrypted off-server backup plus isolated recovery drill, creates an immutable release, activates it atomically, rolls back automatically on failure, and retains only the newest five releases after successful health checks. See `docs/operations.md` for service checks and manual rollback.

## Data Safety

`data/` is the core runtime asset and is not deployed from git. Do not commit, overwrite, delete, or migrate it casually.

Must preserve:

- `data/users.json`
- `data/.encryption_key`
- `data/.flask_secret_key`
- `data/users/<username>/config.json`
- per-user state files, custom todos, schedules, projects, and Apple Calendar token hashes

Usually disposable:

- platform cache files
- worker status files
- short-lived Zhihuishu login session files
- per-user 智慧树 Chromium profiles in the standard encrypted backup policy; users may need to sign in again after a full restore
- logs and lock files

Daily encrypted backups, a scheduled off-server pull, authenticated verification, and an isolated recovery drill are configured. The recovery private key stays off the server. Detailed procedures are in `docs/backup-and-restore.md`.

If the app reports that stored data is temporarily unavailable, do not retry writes; preserve the damaged JSON and follow the corruption-recovery procedure first.
