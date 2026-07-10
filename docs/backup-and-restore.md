# Backup And Restore

`data/` is the runtime source of truth. Deployments intentionally exclude it, so production backup must be handled separately from application code.

## What To Back Up

Back up these files before server maintenance, migration, or destructive local testing:

- `data/users.json`: site account registry and password hashes.
- `data/.encryption_key`: Fernet key for encrypted platform credentials. Losing this makes existing encrypted credentials unreadable.
- `data/.flask_secret_key`: Flask session signing key. Losing this logs users out.
- `data/users/<username>/config.json`: Canvas feed URL, encrypted platform credentials or tokens, and selected course settings.
- `data/users/<username>/custom_todos.json`: user-created todos.
- `data/users/<username>/*_state.json`: hidden, highlighted, and deleted item state.
- `data/users/<username>/zhihuishu_chromium_profile/`: reusable Zhihuishu browser profile. Preserve it when avoiding user relogin matters.
- `data/term_config.json`: local term fallback if customized.

## Usually Disposable

These can normally be rebuilt from platform APIs or runtime behavior:

- `data/users/<username>/*_cache.json`
- `data/users/<username>/zhihuishu_status.json`
- `data/users/<username>/zhihuishu_login_session.json`
- `data/holiday_cache.json`
- `data/term_cache.json`
- `data/server.log`
- `data/zhihuishu_worker.lock`
- Python caches and pytest caches

Cache loss may make the dashboard temporarily empty or slower until the next refresh, but it should not lose user decisions or credentials.

## Backup Procedure

Stop services before taking a file-level snapshot:

```bash
sudo systemctl stop canvas-dashboard.service
sudo systemctl stop zhihuishu-worker.service
sudo systemctl stop zhihuishu-login-cleanup.timer 2>/dev/null || true
cd /home/ubuntu/canvas-dashboard
tar -czf /home/ubuntu/canvas-dashboard-data-$(date +%F).tgz data
```

Restart services after the archive is written:

```bash
sudo systemctl start canvas-dashboard.service
sudo systemctl start zhihuishu-worker.service
sudo systemctl start zhihuishu-login-cleanup.timer 2>/dev/null || true
```

Store the archive somewhere outside the server if the server itself is the failure domain.

Verify that the archive can be read before treating the backup as usable:

```bash
tar -tzf /home/ubuntu/canvas-dashboard-data-YYYY-MM-DD.tgz > /dev/null
```

This project does not yet configure an automatic off-server backup destination. Do not claim that backups are automatic until an operator has selected a destination and encryption-key ownership model.

## JSON Corruption Recovery

When a runtime JSON file cannot be decoded, the app leaves the original file unchanged, writes a sibling copy named `<file>.corrupt-<timestamp>`, logs the incident, and returns HTTP 503 instead of replacing the data with an empty default.

1. Stop the affected service before editing files.
2. Inspect the original and `.corrupt-*` copy; they contain the same damaged bytes captured at detection time.
3. Restore the affected file from a verified backup, or repair it manually only after keeping another copy.
4. Start the services and confirm `curl -fsS http://127.0.0.1:5000/healthz` succeeds.

Never replace `.encryption_key` while restoring a `config.json`; encrypted platform credentials require the matching key.

## Restore Procedure

Stop services, keep a safety copy of the current data directory, restore the archive, and check ownership:

```bash
sudo systemctl stop canvas-dashboard.service
sudo systemctl stop zhihuishu-worker.service
cd /home/ubuntu/canvas-dashboard
mv data data.restore-safety-$(date +%F-%H%M%S)
tar -xzf /path/to/canvas-dashboard-data-YYYY-MM-DD.tgz
sudo chown -R ubuntu:ubuntu data
```

Start services and verify locally:

```bash
sudo systemctl start canvas-dashboard.service
sudo systemctl start zhihuishu-worker.service
sudo systemctl start zhihuishu-login-cleanup.timer 2>/dev/null || true
curl -fsS http://127.0.0.1:5000/healthz
```

If `.encryption_key` was not restored with `config.json`, ask users to re-enter encrypted platform credentials.
