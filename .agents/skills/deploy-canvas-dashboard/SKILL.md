---
name: deploy-canvas-dashboard
description: Use when deploying, uploading, syncing, shipping, restarting, rolling back, or putting Canvas Dashboard changes live on its production server.
---

# Deploy Canvas Dashboard

Run the repository deployment script exactly; do not reimplement its release sequence with ad hoc `scp`, extraction, or service commands.

## Deploy

From the project root:

```powershell
./.agents/skills/deploy-canvas-dashboard/scripts/deploy.ps1
```

The script is the source of truth. It currently:

1. runs `scripts/test.ps1` and Python compilation;
2. creates and downloads an encrypted production-data backup, verifies it, and performs an isolated recovery drill;
3. uses strict SSH host-key checking with `deploy/known_hosts`;
4. uploads an immutable timestamped release under `/home/ubuntu/canvas-dashboard/releases/` without `data/`, `.venv/`, `.git/`, caches, or agent directories;
5. atomically switches `/home/ubuntu/canvas-dashboard/current`;
6. installs systemd/nginx configuration and restarts `canvas-dashboard.service` plus `zhihuishu-worker.service`;
7. verifies both services, `zhihuishu-login-cleanup.timer`, `canvas-dashboard-backup.timer`, nginx, local `/healthz`, and HTTPS `/healthz`;
8. restores the previous release automatically if activation or health verification fails;
9. after successful verification, keeps the newest five releases while always protecting the active and recorded rollback targets.

Do not use `-SkipPreDeployBackup` unless the user explicitly accepts skipping the off-server backup and recovery drill.

## Report

Report the activated release name and the exact verification result. If the script exits nonzero, report that deployment failed or rolled back; do not claim production is updated.

For manual rollback, service diagnostics, backup recovery, or certificate operations, follow `docs/operations.md` and `docs/backup-and-restore.md`.
