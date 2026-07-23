# Production Operations

Production is served at `https://canvas-dashboard.xyz` on `ubuntu@124.222.188.101`. nginx redirects HTTP to HTTPS and proxies the application to `127.0.0.1:5000`.

## Safe Deployment

Run deployments from the repository root on Windows:

```powershell
.\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

The deploy script:

1. runs `scripts/test.ps1` and Python compilation;
2. creates, downloads, verifies, and restores an encrypted backup in an isolated recovery drill;
3. packages only production runtime and deployment files, excluding local docs, tests, Windows helpers, `.git`, `.venv`, `data/`, caches, and agent directories;
4. uploads an immutable release through SSH with the pinned `deploy/known_hosts`;
5. atomically activates `releases/<release-name>`;
6. installs systemd and nginx configuration;
7. restarts services and checks local and HTTPS health;
8. restores the previous release automatically if activation or health checks fail;
9. after successful health checks, keeps the newest five releases while always protecting the active and recorded rollback targets.

OpenSSH must be able to authenticate non-interactively through the configured key or agent. `-SkipPreDeployBackup` exists for an explicit emergency decision; it skips the off-server backup and recovery drill and should not be the normal path.

Runtime `data/` is never included in a release archive.

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
| `certbot.timer` | Renews the Let's Encrypt certificate |
| `nginx.service` | TLS termination, redirects, proxying, and noVNC authorization |

Routine status check:

```bash
systemctl is-active \
  canvas-dashboard.service \
  zhihuishu-worker.service \
  zhihuishu-login-cleanup.timer \
  canvas-dashboard-backup.timer \
  certbot.timer \
  nginx
systemctl list-timers \
  zhihuishu-login-cleanup.timer \
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
journalctl -u canvas-dashboard-backup.service -n 50 --no-pager
sudo nginx -t
sudo tail -n 100 /var/log/nginx/error.log
docker ps --filter "label=canvas-dashboard=tongji-login"
docker ps --filter "label=canvas-dashboard=zhihuishu-login"
```

Do not print `config.json`, encryption keys, session keys, subscription URLs, platform tokens, cookies, or decrypted backup contents into shared logs.

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
- Certificate issue: keep port 80 ACME challenge handling intact, inspect `certbot.timer`, then validate nginx before reload.
