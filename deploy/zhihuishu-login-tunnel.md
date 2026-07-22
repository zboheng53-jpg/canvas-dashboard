# Browser Login Sessions

This app lets normal site users log in to Zhihuishu without SSH, server terminal access, or a shared server desktop.

## User Flow

1. User opens `https://canvas-dashboard.xyz`.
2. User logs in with their site account.
3. User opens the Zhihuishu login page from the dashboard.
4. User clicks "打开智慧树登录窗口".
5. The browser opens a short-lived tokenized URL under the same site.
6. User completes Zhihuishu login and slider inside that window.
7. User returns to the Zhihuishu page and clicks "我已完成登录".
8. The app checks the user's isolated Chromium profile and stops the temporary login container.

Users never need:

- SSH
- noVNC server addresses
- `127.0.0.1:6080`
- `124.222.188.101:6080`
- Ubuntu terminal access
- server passwords

## Admin Deployment

Ordinary application releases are installed by the verified deployment workflow in `docs/operations.md`. The same restricted browser image serves Zhihuishu login and Tongji enhanced authentication. Rebuild it whenever its Dockerfile or entrypoint changes:

```bash
cd /home/ubuntu/canvas-dashboard/current
sudo bash deploy/build-zhihuishu-login-image.sh
```

Allow the service user to start the restricted login containers:

```bash
sudo usermod -aG docker ubuntu
sudo systemctl restart canvas-dashboard
```

After changing group membership, log out and back in before testing shell commands as `ubuntu`.

Install Python dependencies and Chromium for the worker:

```bash
cd /home/ubuntu/canvas-dashboard
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

Release activation installs and enables the worker and cleanup units from `current/deploy/`. For a manual repair:

```bash
cd /home/ubuntu/canvas-dashboard/current
sudo install -m 0644 deploy/zhihuishu-worker.service /etc/systemd/system/
sudo install -m 0644 deploy/zhihuishu-login-cleanup.service /etc/systemd/system/
sudo install -m 0644 deploy/zhihuishu-login-cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zhihuishu-worker.service
sudo systemctl enable --now zhihuishu-login-cleanup.timer
```

Do not replace the live HTTPS nginx file with the HTTP bootstrap file. A release automatically chooses `canvas-dashboard.https.nginx` when the certificate exists. For a manual repair:

```bash
cd /home/ubuntu/canvas-dashboard/current
sudo install -m 0644 deploy/canvas-dashboard.https.nginx /etc/nginx/sites-enabled/canvas-dashboard
sudo nginx -t
sudo systemctl reload nginx
```

## Worker Behavior

- `zhihuishu-worker.service` runs `zhihuishu_worker.py --all-users`.
- Every round rediscovers user directories, so accounts created after service start are included automatically.
- Each user refresh runs in an isolated child process with a default 180-second timeout.
- A timeout or failure updates only that user's status and does not block later users.
- Successful refreshes write `last_success_at`; `/healthz` summarizes newest/oldest success times and age without triggering a browser.

## Security Notes

- Do not expose container ports publicly. `zhihuishu_login_sessions.py` binds each browser container to `127.0.0.1:<port>`.
- Public access goes only through nginx paths like `/zhs-vnc/<port>/<token>/...`.
- nginx calls Flask `/api/zhihuishu/login-session-auth` before proxying noVNC traffic.
- Flask validates the token, port, TTL, and logged-in site account.
- Each container mounts only `data/users/<username>/zhihuishu_chromium_profile` into `/profile`.
- Login sessions expire after 10 minutes.
- A user can have only one active Zhihuishu login session; starting a new one stops the old container.
- `zhihuishu-login-cleanup.timer` removes expired session files and orphaned login containers every 5 minutes.

## Diagnostics

```bash
systemctl status zhihuishu-worker.service
journalctl -u zhihuishu-worker.service -n 100 --no-pager
systemctl list-timers zhihuishu-login-cleanup.timer
journalctl -u zhihuishu-login-cleanup.service -n 50 --no-pager
docker ps --filter "label=canvas-dashboard=zhihuishu-login"
curl -fsS http://127.0.0.1:5000/healthz
```

If a user reports that the login window does not open, check:

```bash
sudo nginx -t
docker images | grep canvas-dashboard-zhihuishu-login
```

Manual cleanup command:

```bash
cd /home/ubuntu/canvas-dashboard/current
../.venv/bin/python zhihuishu_login_sessions.py --cleanup-expired
```
