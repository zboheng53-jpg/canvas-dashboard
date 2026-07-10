# Canvas Dashboard

Flask web app for a personal Tongji University homework dashboard. It aggregates unfinished work from Canvas, Haoke, Zhixuemeng, Zhihuishu, and manual todos.

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

## Temporary iPhone Calendar Test (Paused)

The helper below verifies the initial subscription flow without reading or changing `data/`:

```powershell
.\scripts\apple-calendar-mobile-test.ps1
```

It starts an isolated temporary app, creates one fake all-day task, prints a one-time HTTPS subscription URL, and removes the tunnel and temporary data when you press `Ctrl+C`. In iPhone Calendar, choose **Add Calendar** → **Add Subscription Calendar** and paste that URL. It never uses the production server or real local account data.

Do not retry this helper on the current network: its Cloudflare Quick Tunnel cannot establish the required outbound connection and returns Error 1033. Resume only from a network that permits the tunnel connection, or after the production domain, ICP filing, and HTTPS are ready.

## Deploy

Reference deployment files live in `deploy/`.

```bash
cd /home/ubuntu/canvas-dashboard
.venv/bin/python serve.py
```

Production normally runs through systemd using `deploy/canvas-dashboard.service`; nginx proxies public HTTP to `127.0.0.1:5000`. The unauthenticated local health endpoint is:

```bash
curl -fsS http://127.0.0.1:5000/healthz
```

`canvas-dashboard.xyz` is awaiting review. Keep production on its current IP/HTTP path until domain review and ICP filing are complete; only then enable HTTPS and secure session cookies.

Apple Calendar's private ICS routes are implemented for local verification only. Do not deploy or share subscription URLs until the domain, ICP filing, HTTPS, token-safe proxy logging, and a real-iPhone test are all complete. The current local test covers subscription, cached-task display, and revocation; it does not yet verify calendar notifications.

Zhihuishu background refresh and noVNC login windows need the worker service, Docker image, and cleanup timer described in `deploy/zhihuishu-login-tunnel.md`.

## Data Safety

`data/` is the core runtime asset and is not deployed from git. Do not commit, overwrite, delete, or migrate it casually.

Must preserve:

- `data/users.json`
- `data/.encryption_key`
- `data/.flask_secret_key`
- `data/users/<username>/config.json`
- per-user state files and custom todos
- per-user Zhihuishu Chromium profiles if long-lived login state matters

Usually disposable:

- platform cache files
- worker status files
- short-lived Zhihuishu login session files
- logs and lock files

Detailed backup and restore guidance is in `docs/backup-and-restore.md`.
If the app reports that stored data is temporarily unavailable, do not retry writes; follow that document's JSON-corruption recovery procedure first.
