# Production Operations

Production is served at `https://canvas-dashboard.xyz` on `ubuntu@124.222.188.101`. nginx redirects HTTP to HTTPS and proxies the application to `127.0.0.1:5000`.

## Safe Deployment

Run deployments from the repository root on Windows:

```powershell
.\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

The deploy script:

1. verifies clean `main` against the live remote `origin/main`, records the commit, and runs `scripts/test.ps1 -Suite all` plus Python compilation;
2. creates, downloads, verifies, and restores an encrypted backup in an isolated recovery drill;
3. rechecks the unchanged clean, pushed commit after tests/backup, archives that fixed commit (release name includes its first 12 characters), and packages only production runtime and deployment files, excluding local docs, tests, Windows helpers, `.git`, `.venv`, `data/`, caches, and agent directories;
4. uploads an immutable release through SSH with the pinned `deploy/known_hosts`;
5. atomically activates `releases/<release-name>`;
6. installs systemd and nginx configuration;
7. restarts services and checks local and HTTPS health;
8. restores the previous release automatically if activation or health checks fail;
9. after successful health checks, keeps the newest five releases while always protecting the active and recorded rollback targets.

OpenSSH must be able to authenticate non-interactively through the configured key or agent. `-SkipPreDeployBackup` exists for an explicit emergency decision; it skips the off-server backup and recovery drill and should not be the normal path.

Runtime `data/` is never included in a release archive.

New releases create their own `.venv/` and record `dependencies.txt`; web,
worker and cleanup units execute `current/.venv/bin/python`. The login image is
recorded by immutable Docker ID in each release's `release.env`. Legacy rollback
targets retain the old shared environment until replaced. Activation, backup
and rollback serialize through `.maintenance.lock`; all activation checks,
including HTTPS and final service checks, share the failure rollback handler.
These templates require an actual Linux deployment check before release; local
fault-injection tests verify control flow without modifying production.

Nginx drops client-supplied forwarded Host/Prefix for dashboard requests and
uses a fixed HTTPS redirect target. VNC locations disable access/error logs to
keep URL tokens out of logs; use authenticated session metadata and service
logs for login diagnostics. Separate domains for the other applications remain
an operator infrastructure decision.

Waitress defaults to eight request threads (`CANVAS_DASHBOARD_THREADS` overrides this). All five ordinary HTTP platforms share a bounded background executor, and their read endpoints return cached projections immediately. Explicit slow authentication operations return a task handle. The request pool remains available for local reads while upstream work runs; increasing it does not replace moving slow requests out of Web handlers.

OJ reads only the top-level assignment list, using an 8-second connection timeout and a 45-second read timeout (`TONGJIOJ_READ_TIMEOUT_SECONDS` overrides the latter), with at most one retry for timeouts, connection failures, or 502/503/504 responses. Exhausting the retry preserves existing assignments and reports synchronization failure; expired sessions are renewed separately. Cached cookies are restored with the OJ host scope so server rotation replaces them, and renewed cookies are persisted after the assignment page succeeds.

OJ completion is manual; submission records and grades are never fetched or used to remove assignments. Cache version 3 marks older projections stale while retaining them until a successful refresh. Stable assignment IDs, local state, and external subtasks remain unchanged; no user-data migration or state reset is required.

## Runtime File Permissions

The application and 智慧树 worker use `UMask=0077`; runtime files are created private by default. Release activation corrects `/home/ubuntu/canvas-dashboard/data` to `ubuntu:ubuntu`, directories to `0700`, and files to `0600`. This includes credentials, session/key files, and user configuration. Verify after a release without printing any sensitive file contents:

```bash
stat -c '%a %U:%G %n' /home/ubuntu/canvas-dashboard/data \
  /home/ubuntu/canvas-dashboard/data/.flask_secret_key \
  /home/ubuntu/canvas-dashboard/data/.encryption_key
find /home/ubuntu/canvas-dashboard/data/users -maxdepth 1 -type d -printf '%m %u:%g %p\n'
systemd-analyze security canvas-dashboard.service
systemd-analyze security zhihuishu-worker.service
```

The two services enable `PrivateTmp`, kernel/control-group protection, `NoNewPrivileges`, `RestrictSUIDSGID`, and `LockPersonality`. They intentionally retain normal network access, release/current access, Chromium, Docker-socket access, user data, logs, and the existing encrypted-backup flow; test login windows and a worker cycle after any future sandboxing change.

The Chromium worker also starts after `user@1000.service` and receives `XDG_RUNTIME_DIR=/run/user/1000` for the production `ubuntu` account (UID 1000). This directory must belong to that user and remain available for background browser sessions; production already enables lingering for `ubuntu`. A worker without this runtime environment can time out reading a page body even when navigation returns HTTP 200. Compare actual session checks under the service environment before weakening protection settings or clearing status files.

## Small-group admission controls

Set overrides in `/etc/canvas-dashboard/canvas-dashboard.env`, then restart the affected web/worker services. Production requires `CANVAS_DASHBOARD_ENV=production`, `CANVAS_DASHBOARD_COOKIE_SECURE=1`, and a fixed HTTPS `CANVAS_DASHBOARD_PUBLIC_BASE_URL` or explicit `CANVAS_DASHBOARD_TRUSTED_HOSTS`; the supplied web unit sets the production defaults and allows operator overrides through its environment file. `CANVAS_DASHBOARD_REGISTRATION_ENABLED=0` pauses new registrations without blocking existing logins.

`CANVAS_DASHBOARD_LOGIN_MAX_SESSIONS=1` (default) caps both interactive login platforms and the 智慧树 background browser. Capacity/profile coordination uses cross-process locks and resource records under the shared data root. It is local-machine coordination, not a distributed semaphore. An active login record blocks the same user's worker even if the global limit is raised. Docker stop failure retains metadata/occupation for retry; do not erase leases or profiles to make room without confirming their resources have exited. Startup and completion are background operations: the initial request returns 202, and task status reports any capacity rejection as 429. The retired password-based timetable refresh endpoint returns 410 and never starts Chromium.

### Registration capacity guard

`capacity_guard.py` is the admission brake for new registrations. It aggregates three metrics from the data root (counts only, never usernames) and closes `/api/auth/register` as soon as one threshold is reached. `/register` then renders the explanation panel instead of the form — the left showcase is unchanged — and the login page replaces its “立即注册” hint. Login, logout and all existing-account data access are unaffected, and the API rejects direct calls with `registration_closed` plus the same reason, so the UI cannot be bypassed.

| Variable | Default | Metric |
| --- | --- | --- |
| `CANVAS_DASHBOARD_CAPACITY_GUARD_ENABLED` | `1` | Evaluate the thresholds; `0` disables automatic closure (the manual pause still applies) |
| `CANVAS_DASHBOARD_CAPACITY_MAX_TOTAL_USERS` | `15` | Registered accounts, any status except `deleting` |
| `CANVAS_DASHBOARD_CAPACITY_MAX_ACTIVE_USERS` | `10` | Accounts active within the window below |
| `CANVAS_DASHBOARD_CAPACITY_MAX_CONNECTED_PLATFORMS` | `40` | Sum of `connected` platform entries across accounts |
| `CANVAS_DASHBOARD_CAPACITY_ACTIVE_WINDOW_DAYS` | `14` | Activity window; activity is the later of `last_login_at` and the per-user presence stamp (`.capacity_presence.json`, entries pruned after 90 days) |

A threshold of `0` (or a negative value) disables that single gate. `CANVAS_DASHBOARD_REGISTRATION_ENABLED=0` stays the manual pause and takes precedence. These are admission limits for the current single-process deployment, not a measured maximum concurrency; revise them with the operating thresholds in [small-group launch notes](small-group-launch.md).

Inspect the current decision on the host:

```bash
cd /home/ubuntu/canvas-dashboard/current
.venv/bin/python scripts/capacity_guard.py status
.venv/bin/python scripts/capacity_guard.py status --json
```

`data/.capacity_guard_state.json` records a username-free latch of the last state change (counts, thresholds, reason codes). An unreadable metric file (corrupt JSON) closes registration with reason `capacity_check_failed` instead of assuming there is room left; repair the file per [backup and restore](backup-and-restore.md) before expecting an automatic reopen. Registration reopens by itself once the counts drop below the thresholds, or when an operator raises the limits after the capacity work is finished.

Canvas, 好课, 智学盟, 课堂派 and 同济 OJ share the `HTTP_SYNC_MAX_WORKERS=2` / `HTTP_SYNC_MAX_JOBS=32` budget, including queued and running jobs. Jobs deduplicate by username, platform and job type. Platforms no longer create their own HTTP fetch pools or per-user sync threads. Refresh, weather and explicit slow login operations use this budget; reads return cached/pending responses immediately. `cache_only=1` polls never restart a failed refresh. Set either limit in the Web service environment and restart to apply it. This budget belongs to the single Web process; do not run extra Web instances as a way to increase capacity.

## Static resources, request boundaries and retired applications

Production `/static/` uses nginx `alias` to `current/frontend/assets/`, without a proxy to Waitress. Built CSS/JS with the generated 20-character content hash use `public, max-age=31536000, immutable`; source files use `public, no-cache`. The installer gives nginx traversal and read access to public assets while retaining 0700/0600 on runtime data. Flask still serves static files for development. `scripts/check_nginx_boundaries.py` runs an independent loopback nginx instance to test content, headers, VNC HTTP/WebSocket authentication and body limits without changing the live configuration.

Both nginx templates explicitly set `client_max_body_size 8m`; Flask `MAX_CONTENT_LENGTH` is `8 * 1024 * 1024` bytes. Change both together. VNC `auth_request` sends the Dashboard cookie only to Flask; the actual container request removes Cookie and Authorization, and container Set-Cookie is hidden.

The discontinued `/daily-english` and `/life-list` paths return 410. Historical application retirement is separate from normal Dashboard deployment. The prior retirement used `deploy/retire-unused-apps.sh` to archive the two applications under `/home/ubuntu/.retired-dashboard-apps/`; a Dashboard rollback does not restart them.

## Basic operational monitoring

`canvas-dashboard-monitor.timer` runs every minute. Its journal contains JSON resource samples: MemAvailable, swap use and in/out rates, load average, disk use, OOM counter changes, active browser occupation, aggregate queue status, recent Web status and the number of accounts repeatedly failing per platform. The Web log records endpoint name (no URL parameters), status and duration; sync events include platform, job type, queued/running/success/failed/cancelled, duration and last success. Browser events include startup duration, global available-memory change and end reason; the memory delta is an observation of the whole machine, not exclusive Chromium RSS.

Authenticated `GET /api/diagnostics/runtime` returns current aggregate system/Web/sync/browser status, including the real Waitress queued/active/thread counts, plus an `admission` block with the registration-capacity decision, thresholds and metrics. It excludes usernames, credentials and task tokens. Last Web and sync snapshots are local JSON files for the independent sampler. After process restart, inspect durable per-user sync metadata for failure history; executor counters describe the current Web process.

```bash
journalctl -u canvas-dashboard-monitor.service --since '15 minutes ago' -o cat
journalctl -u canvas-dashboard.service --since '15 minutes ago'
systemctl status canvas-dashboard-monitor.timer
```

Investigate local API p95 persistently above 1 second, available memory below 300 MiB, sustained swap traffic (initial warning at 1 MiB/s), any new OOM kill, disk use at 80%, or queued work older than 5 minutes. Compare successive samples; a nonzero swap allocation alone is not ongoing swap traffic. These are journal/manual-check thresholds, not external notification delivery. Weather and holiday cache limitations are documented in `docs/development.md`; real platform credentials and production peak memory still need observation after release.

Canvas feed hosts are restricted to `canvas.tongji.edu.cn` by default. For another institution, set `CANVAS_DASHBOARD_CANVAS_FEED_HOSTS` to comma-separated, operator-verified hostnames. Only HTTPS on port 443 is accepted; redirects are not followed. Do not add user-controlled hosts. Existing untrusted feed URLs retain their old cache but will fail refresh until corrected. See [small-group launch notes](small-group-launch.md) for measured capacity context and operating thresholds.

## Release Inspection And Rollback

Inspect the active and previous releases:

```bash
readlink -f /home/ubuntu/canvas-dashboard/current
cat /home/ubuntu/canvas-dashboard/.previous-release
ls -1dt /home/ubuntu/canvas-dashboard/releases/*
```

Roll back to the recorded previous release:

```bash
bash /home/ubuntu/canvas-dashboard/current/deploy/rollback-release.sh
```

Or pass an explicit release directory:

```bash
bash /home/ubuntu/canvas-dashboard/current/deploy/rollback-release.sh \
  /home/ubuntu/canvas-dashboard/releases/release-YYYYMMDDTHHMMSSZ
```

The rollback script rejects targets outside `releases/`, reinstalls the target's service/nginx configuration, restarts the app and worker, and verifies health. It does not replace `data/`.

Normal deployments prune older immutable releases automatically. Do not manually delete `current` or the path recorded in `.previous-release`; the installer protects both even if either falls outside the newest five.

## Services And Timers

| Unit | Purpose |
| --- | --- |
| `canvas-dashboard.service` | Waitress application from `current/` |
| `zhihuishu-worker.service` | All-user 智慧树 supervisor |
| `zhihuishu-login-cleanup.timer` | Removes expired login sessions and containers every five minutes |
| `canvas-dashboard-backup.timer` | Creates a daily encrypted server-side data backup |
| `canvas-dashboard-account-cleanup.timer` | Daily conservative cleanup of 90-day blank accounts, pending deletions and isolated directories |
| `certbot.timer` | Renews the Let's Encrypt certificate |
| `nginx.service` | TLS termination, redirects, proxying, and noVNC authorization |

Routine status check:

```bash
systemctl is-active \
  canvas-dashboard.service \
  zhihuishu-worker.service \
  zhihuishu-login-cleanup.timer \
  canvas-dashboard-account-cleanup.timer \
  canvas-dashboard-backup.timer \
  canvas-dashboard-monitor.timer \
  certbot.timer \
  nginx
systemctl list-timers \
  zhihuishu-login-cleanup.timer \
  canvas-dashboard-account-cleanup.timer \
  canvas-dashboard-backup.timer \
  canvas-dashboard-monitor.timer \
  certbot.timer \
  --all --no-pager
```

## Health Checks

Local:

```bash
curl -fsS http://127.0.0.1:5000/healthz
```

Public:

```bash
curl -fsS https://canvas-dashboard.xyz/healthz
curl -fsSI http://canvas-dashboard.xyz/
```

`/healthz` is public and performs only local checks. It reports application state, `data/` writability, 智慧树 status counts, newest and oldest `last_success_at`, last-success age, and lock-file presence. It never launches a refresh or calls an upstream platform.

An old `last_success_at` with no worker error means the process is reachable but data may be stale; investigate the worker log and the affected user's status file.

## Logs And Diagnostics

```bash
journalctl -u canvas-dashboard.service -n 100 --no-pager
journalctl -u zhihuishu-worker.service -n 100 --no-pager
journalctl -u zhihuishu-login-cleanup.service -n 50 --no-pager
journalctl -u canvas-dashboard-account-cleanup.service -n 50 --no-pager
journalctl -u canvas-dashboard-backup.service -n 50 --no-pager
sudo nginx -t
sudo tail -n 100 /var/log/nginx/error.log
docker ps --filter "label=canvas-dashboard=tongji-login"
docker ps --filter "label=canvas-dashboard=zhihuishu-login"
```

Do not print `config.json`, encryption keys, session keys, subscription URLs, platform tokens, cookies, or decrypted backup contents into shared logs.

## Account Administration

Run account administration only on the production host or a trusted maintenance workstation. Suspension and password reset invalidate existing sessions; a resumed account must sign in again.

```bash
cd /home/ubuntu/canvas-dashboard/current
.venv/bin/python scripts/account_admin.py suspend <username> --reason "<ticket or incident reason>"
.venv/bin/python scripts/account_admin.py resume <username> --reason "<ticket or incident reason>"
.venv/bin/python scripts/account_admin.py issue-reset <username>
```

`issue-reset` prints a one-time credential valid for 30 minutes. Deliver it through an approved private channel, do not copy it into shared logs, and direct the user to `/reset-password`. Permanent account deletion is user-initiated in **偏好设置**; it requires the current password and the exact confirmation text `永久删除`.

## HTTPS And Environment

Production environment flags are stored in:

```text
/etc/canvas-dashboard/canvas-dashboard.env
```

The active HTTPS deployment requires:

```text
CANVAS_DASHBOARD_COOKIE_SECURE=1
CANVAS_DASHBOARD_ENV=production
CANVAS_DASHBOARD_PUBLIC_BASE_URL=https://canvas-dashboard.xyz
CANVAS_DASHBOARD_ICP_NUMBER=闽ICP备2026026558号-1
CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED=1
```

Check certificate and renewal state:

```bash
sudo certbot certificates
systemctl status certbot.timer --no-pager
sudo certbot renew --dry-run
```

`deploy/enable-https.sh` is the one-time bootstrap. It verifies both DNS names resolve to the expected server, obtains the certificate, enables the HTTPS nginx configuration, enables secure cookies and Apple Calendar, and verifies the redirect plus TLS endpoint. It is not needed for ordinary deployments.

## Incident Boundaries

- JSON corruption: stop writes to the affected file and follow `docs/backup-and-restore.md`; never replace it with an empty object.
- Pending account deletion: deleting records are inactive and retryable. The deletion ledger must be saved before data is isolated. The cleanup timer retries resource/isolation failures and purges only managed quarantine entries. A deletion may have completed account removal while physical purge is pending; preserve that distinction when answering users.
- Bad release: use `rollback-release.sh`; do not edit an immutable release in place.
- 智慧树 login/worker or Tongji enhanced-auth window issue: follow `deploy/zhihuishu-login-tunnel.md`.
- Data loss or key mismatch: stop the app and worker before any restore; follow the staged restore procedure in `docs/backup-and-restore.md`.
- Accidental account restoration: preserve and apply the live `data/.account_deletion_ledger.json` during the staged restore; it prevents an older archive from reviving a deleted immutable account ID.
- Certificate issue: keep port 80 ACME challenge handling intact, inspect `certbot.timer`, then validate nginx before reload.

## Health and assets

`/livez` checks Web responsiveness; `/readyz` checks the local critical storage and users registry without writing probe files. `/healthz` stays compatible with deployment checks: worker failure reports degraded with HTTP 200, while critical storage failure returns 503. The authenticated `/api/diagnostics/workers` uses a fresh heartbeat and a live process, rather than the existence of a lock file, to assess the worker. These metadata checks do not prove disk writes will succeed after a later permission/disk change.

Release installation builds CSS/JS fingerprints from source into `frontend/assets/built/`. Nginx serves these files with long caching and compression; source assets must revalidate, and dynamic HTML/API are private/no-store. Do not reuse an old process manifest after rebuilding assets: restart with the new release. The recovery guide documents independent deletion-ledger downloads and the remaining window before a newly deleted account reaches the next off-server copy.
