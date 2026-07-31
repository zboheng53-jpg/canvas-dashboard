#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/canvas-dashboard
domain=canvas-dashboard.xyz
expected_ip=124.222.188.101
current="$root/current"

resolved_ips=$(getent ahostsv4 "$domain" | awk '{print $1}' | sort -u)
if ! grep -Fxq "$expected_ip" <<<"$resolved_ips"; then
    echo "$domain does not resolve to $expected_ip" >&2
    exit 2
fi
www_ips=$(getent ahostsv4 "www.$domain" | awk '{print $1}' | sort -u)
if ! grep -Fxq "$expected_ip" <<<"$www_ips"; then
    echo "www.$domain does not resolve to $expected_ip" >&2
    exit 2
fi

sudo install -d -m 0755 /var/www/certbot /etc/canvas-dashboard
sudo install -m 0644 "$current/deploy/canvas-dashboard.nginx" /etc/nginx/sites-enabled/canvas-dashboard
sudo nginx -t
sudo systemctl reload nginx

if ! command -v certbot >/dev/null 2>&1; then
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y certbot
fi

sudo certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --domain "$domain" \
    --domain "www.$domain" \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email \
    --keep-until-expiring

sudo install -m 0644 "$current/deploy/canvas-dashboard.https.nginx" /etc/nginx/sites-enabled/canvas-dashboard
{
    printf 'CANVAS_DASHBOARD_COOKIE_SECURE=1\n'
    printf 'CANVAS_DASHBOARD_ICP_NUMBER=闽ICP备2026026558号-1\n'
    printf 'CANVAS_DASHBOARD_APPLE_CALENDAR_ENABLED=1\n'
} | sudo tee /etc/canvas-dashboard/canvas-dashboard.env >/dev/null
sudo chmod 0644 /etc/canvas-dashboard/canvas-dashboard.env
sudo nginx -t
sudo systemctl restart canvas-dashboard.service
sudo systemctl reload nginx

for attempt in $(seq 1 30); do
    if curl -fsS --max-time 10 \
        --resolve "$domain:443:127.0.0.1" \
        "https://$domain/healthz" >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "HTTPS health check failed" >&2
        exit 1
    fi
    sleep 2
done

curl -fsSI --max-time 10 \
    --resolve "$domain:80:127.0.0.1" \
    "http://$domain/" | grep -F "301"
curl -fsS --max-time 10 \
    --resolve "$domain:443:127.0.0.1" \
    "https://$domain/healthz"
