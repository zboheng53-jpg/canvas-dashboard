# Zhihuishu User Login Sessions

This app lets normal site users log in to Zhihuishu without SSH, server terminal access, or a shared server desktop.

## User Flow

1. User opens `http://124.222.188.101`.
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

Build the restricted browser image:

```bash
cd /home/ubuntu/canvas-dashboard
sudo docker build -f deploy/zhihuishu-login-browser.Dockerfile -t canvas-dashboard-zhihuishu-login:latest .
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

Install the worker service:

```bash
sudo cp deploy/zhihuishu-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zhihuishu-worker.service
```

Install nginx config:

```bash
sudo cp deploy/canvas-dashboard.nginx /etc/nginx/sites-enabled/canvas-dashboard
sudo nginx -t
sudo systemctl reload nginx
```

## Security Notes

- Do not expose container ports publicly. `zhihuishu_login_sessions.py` binds each browser container to `127.0.0.1:<port>`.
- Public access goes only through nginx paths like `/zhs-vnc/<port>/<token>/...`.
- nginx calls Flask `/api/zhihuishu/login-session-auth` before proxying noVNC traffic.
- Flask validates the token, port, TTL, and logged-in site account.
- Each container mounts only `data/users/<username>/zhihuishu_chromium_profile` into `/profile`.
- Login sessions expire after 10 minutes.
- A user can have only one active Zhihuishu login session; starting a new one stops the old container.

## Diagnostics

```bash
systemctl status zhihuishu-worker.service
journalctl -u zhihuishu-worker.service -n 100 --no-pager
docker ps --filter "name=canvas-zhs-login"
```

If a user reports that the login window does not open, check:

```bash
sudo nginx -t
docker images | grep canvas-dashboard-zhihuishu-login
```
