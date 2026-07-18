# Backup And Restore

`data/` is the runtime source of truth and is intentionally excluded from deployments. The supported backup format is an authenticated `.cdbak` envelope: RSA-OAEP-SHA256 wraps a random content key, and AES-256-GCM encrypts and authenticates a gzip-compressed tar stream plus a SHA-256 manifest.

## Key Ownership

The server stores only the public encryption key:

```text
/etc/canvas-dashboard/backup-public.pem
```

The recovery key pair and downloaded backups live off-server on the Windows operator machine:

```text
%USERPROFILE%\.canvas-dashboard-backup\private.pem
%USERPROFILE%\.canvas-dashboard-backup\public.pem
%USERPROFILE%\CanvasDashboardBackups\*.cdbak
```

Never upload `private.pem` to the server or commit either key. Losing the private key makes every existing `.cdbak` unreadable. An incomplete key pair is not replaced automatically.

## Included And Excluded Data

The backup contains durable runtime files, including:

- `users.json`, `.encryption_key`, and `.flask_secret_key`;
- per-user `config.json`, `custom_todos.json`, `apple_calendar.json`, `course_schedule.json`, `schedule_items.json`, `projects.json`, and platform state;
- other durable per-user JSON;
- customized `term_config.json`.

Before encryption, every included JSON file must decode as UTF-8 JSON. Backup creation fails rather than archiving malformed JSON.

The standard policy intentionally excludes rebuildable or volatile data:

- `*_cache.json`, `holiday_cache.json`, and `term_cache.json`;
- `zhihuishu_status.json`, login-session metadata, and the worker lock;
- `.corrupt-*` forensic copies and server logs;
- every `zhihuishu_chromium_profile/`.

After a full restore, platform caches refill and 智慧树 users may need to sign in again. If preserving a browser profile for a special migration is required, copy it separately while the app, worker, and login containers are stopped; do not add it casually to the routine encrypted archive.

## Automatic Backup Flow

Production has two layers:

1. `canvas-dashboard-backup.timer` stops the app and worker, creates an encrypted server-side backup, restarts both services, and verifies local health. Server retention is 14 backups.
2. The Windows scheduled task `Canvas Dashboard Encrypted Backup` asks the server to create a backup, downloads the newest `.cdbak`, verifies authenticated encryption plus every manifest entry, and retains 30 local copies.

Inspect automation:

```powershell
Get-ScheduledTask -TaskName "Canvas Dashboard Encrypted Backup"
Get-ScheduledTaskInfo -TaskName "Canvas Dashboard Encrypted Backup"
Get-ChildItem "$HOME\CanvasDashboardBackups" -Filter *.cdbak |
  Sort-Object LastWriteTime -Descending
```

`Ready` proves only that the task is registered. After its first trigger, require `LastTaskResult` to be `0` and confirm a newer local `.cdbak` exists. Until then, describe the schedule as configured but not yet proven by Task Scheduler; a manual `pull-production-backup.ps1` run verifies the same backup/download path but not the scheduler trigger itself.

```bash
systemctl status canvas-dashboard-backup.timer --no-pager
systemctl list-timers canvas-dashboard-backup.timer --all --no-pager
journalctl -u canvas-dashboard-backup.service -n 50 --no-pager
```

Install or repair the Windows task:

```powershell
.\scripts\install-backup-task.ps1
```

## Manual Backup And Recovery Drill

Create a fresh production backup, download it, verify it, and perform a real restore into an isolated temporary directory:

```powershell
.\scripts\pull-production-backup.ps1 -CreateBackup -RecoveryDrill
```

This command does not replace production data. It is the required pre-deployment gate and the preferred periodic recovery exercise.

Verify or restore a selected local archive manually:

```powershell
.\.venv\Scripts\python.exe scripts\backup_data.py verify `
  --input "$HOME\CanvasDashboardBackups\canvas-dashboard-data-....cdbak" `
  --private-key "$HOME\.canvas-dashboard-backup\private.pem"

.\.venv\Scripts\python.exe scripts\backup_data.py restore `
  --input "$HOME\CanvasDashboardBackups\canvas-dashboard-data-....cdbak" `
  --private-key "$HOME\.canvas-dashboard-backup\private.pem" `
  --output-dir "$env:TEMP\canvas-dashboard-restore-review"
```

The restore output contains a `data/` directory. Inspect it in isolation and delete the decrypted temporary copy securely after the exercise.

## JSON Corruption Recovery

When a runtime JSON file cannot be decoded, the app leaves the original file unchanged, writes a sibling copy named `<file>.corrupt-<timestamp>`, logs the incident, and returns HTTP 503 instead of replacing the data with an empty default.

1. Stop the affected service before editing files.
2. Inspect the original and `.corrupt-*` copy; they contain the same damaged bytes captured at detection time.
3. Run `backup_data.py verify` on the selected backup.
4. Restore into a new local directory and copy only the known-good affected file, or stage a full restore as below.
5. Start the services and confirm local and public health.

Never replace `.encryption_key` while restoring a `config.json`; encrypted platform credentials require the matching key.

## Full Production Restore

Do not decrypt a backup on the server by uploading the private key. Restore locally, upload the decrypted `data/` as a staging directory, and swap it only after review.

1. Restore the selected `.cdbak` locally into a new empty directory.
2. Confirm the command reports `ok: true` and the expected file count.
3. Upload the restored `data/` to `/home/ubuntu/canvas-dashboard/data.restore-stage`.
4. On the server, stop the application and worker, preserve the current directory, and activate the staged copy:

```bash
set -e
cd /home/ubuntu/canvas-dashboard
sudo systemctl stop canvas-dashboard.service zhihuishu-worker.service
test -d data.restore-stage
test -f data.restore-stage/users.json
mv data "data.restore-safety-$(date -u +%Y%m%dT%H%M%SZ)"
mv data.restore-stage data
sudo chown -R ubuntu:ubuntu data
sudo systemctl start canvas-dashboard.service zhihuishu-worker.service
```

5. Verify services, timers, local health, and public HTTPS:

```bash
systemctl is-active canvas-dashboard.service zhihuishu-worker.service
curl -fsS http://127.0.0.1:5000/healthz
curl -fsS https://canvas-dashboard.xyz/healthz
```

6. Test one site login, one custom todo, and platform configuration decryption before removing the safety copy.
7. Remove the decrypted local restore directory and server safety copy only after explicit review.

If `.encryption_key` was not restored with `config.json`, existing encrypted platform credentials cannot be recovered from that data set. If `.flask_secret_key` changed, all sessions are invalidated.
