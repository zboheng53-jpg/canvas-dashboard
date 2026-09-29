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

Waitress defaults to eight request threads (`CANVAS_DASHBOARD_THREADS` overrides this). OJ synchronization runs in a separate background thread per active account and is deduplicated; its HTTP endpoints return cached projections immediately. The request pool retains capacity for local reads during bursts of slower calls to the other platforms. Increasing the pool is capacity headroom, not a replacement for keeping slow OJ requests off WSGI threads.

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

Set overrides in `/etc/canvas-dashboard/canvas-dashboard.env`, then restart `canvas-dashboard.service` for them to take effect. `CANVAS_DASHBOARD_REGISTRATION_ENABLED=0` pauses new registrations without blocking existing logins. `CANVAS_DASHBOARD_LOGIN_MAX_SESSIONS=1` (default) caps the combined Tongji/智慧树 interactive login windows; full capacity returns 429 with a retry message. This is a single-Web-process guard, not a cluster semaphore.

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
| `canvas-dashboard-account-cleanup.timer` | Daily conservative cleanup of 90-day blank accounts |
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
  certbot.timer \
  nginx
systemctl list-timers \
  zhihuishu-login-cleanup.timer \
  canvas-dashboard-account-cleanup.timer \
  canvas-dashboard-backup.timer \
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
../.venv/bin/python scripts/account_admin.py suspend <username> --reason "<ticket or incident reason>"
../.venv/bin/python scripts/account_admin.py resume <username> --reason "<ticket or incident reason>"
../.venv/bin/python scripts/account_admin.py issue-reset <username>
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
- Bad release: use `rollback-release.sh`; do not edit an immutable release in place.
- 智慧树 login/worker or Tongji enhanced-auth window issue: follow `deploy/zhihuishu-login-tunnel.md`.
- Data loss or key mismatch: stop the app and worker before any restore; follow the staged restore procedure in `docs/backup-and-restore.md`.
- Accidental account restoration: preserve and apply the live `data/.account_deletion_ledger.json` during the staged restore; it prevents an older archive from reviving a deleted immutable account ID.
- Certificate issue: keep port 80 ACME challenge handling intact, inspect `certbot.timer`, then validate nginx before reload.
