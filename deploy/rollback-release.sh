#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/canvas-dashboard
target=${1:-}
if [ -z "$target" ]; then
    target=$(cat "$root/.previous-release")
fi
target=$(readlink -f "$target")
case "$target" in
    "$root"/releases/*) ;;
    *) echo "Refusing unsafe rollback target: $target" >&2; exit 2 ;;
esac
test -f "$target/app.py"

current=$(readlink -f "$root/current")
printf '%s\n' "$current" > "$root/.previous-release"
ln -sfn "$target" "$root/current.next"
mv -Tf "$root/current.next" "$root/current"

for unit in \
    canvas-dashboard.service \
    zhihuishu-worker.service \
    zhihuishu-login-cleanup.service \
    zhihuishu-login-cleanup.timer \
    canvas-dashboard-backup.service \
    canvas-dashboard-backup.timer
do
    if [ -f "$target/deploy/$unit" ]; then
        sudo install -m 0644 "$target/deploy/$unit" "/etc/systemd/system/$unit"
    fi
done
nginx_source="$target/deploy/canvas-dashboard.nginx"
if sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem &&
   [ -f "$target/deploy/canvas-dashboard.https.nginx" ]; then
    nginx_source="$target/deploy/canvas-dashboard.https.nginx"
fi
sudo install -m 0644 "$nginx_source" /etc/nginx/sites-enabled/canvas-dashboard
sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl restart canvas-dashboard.service zhihuishu-worker.service
sudo systemctl try-restart zhihuishu-login-cleanup.timer canvas-dashboard-backup.timer
sudo systemctl reload nginx
for attempt in $(seq 1 20); do
    if curl -fsS --max-time 5 http://127.0.0.1:5000/healthz >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 20 ]; then
        echo "Rollback health check failed" >&2
        exit 1
    fi
    sleep 1
done
if sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem; then
    curl -fsS --max-time 10 \
        --resolve canvas-dashboard.xyz:443:127.0.0.1 \
        https://canvas-dashboard.xyz/healthz >/dev/null
fi
echo "Rolled back to $(basename "$target")"
