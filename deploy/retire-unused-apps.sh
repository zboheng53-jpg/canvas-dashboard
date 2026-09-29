#!/usr/bin/env bash
# One-time retirement authorized for these two applications only.
set -euo pipefail
umask 077
archive=/home/ubuntu/.retired-dashboard-apps
mkdir -p "$archive"
chmod 0700 "$archive"
if [ -f "$archive/finished" ]; then
    echo "Unused applications already retired"
    exit 0
fi
subdomains=/etc/nginx/conf.d/project-subdomains.conf
if [ -f "$subdomains" ]; then
  if [ ! -f "$archive/project-subdomains.conf" ]; then
    # Refuse to replace this file if it has gained unrelated virtual hosts.
    sudo python3 - "$subdomains" <<'PY'
from pathlib import Path
import re,sys
text=Path(sys.argv[1]).read_text()
names=re.findall(r'\bserver_name\s+([^;]+);',text)
assert sorted(name.strip() for name in names)==['english.canvas-dashboard.xyz','life.canvas-dashboard.xyz'], 'Unexpected virtual hosts'
assert len(re.findall(r'\bserver\s*\{',text))==2, 'Unexpected server blocks'
PY
    sudo cp -p "$subdomains" "$archive/project-subdomains.conf"
    sudo chown ubuntu:ubuntu "$archive/project-subdomains.conf"
  fi
    cat > "$archive/retired-subdomains.conf" <<'NGINX'
server { listen 80; listen [::]:80; server_name english.canvas-dashboard.xyz life.canvas-dashboard.xyz; return 410; }
NGINX
    sudo install -m 0644 "$archive/retired-subdomains.conf" "$subdomains"
    if ! sudo nginx -t; then
        sudo cp -p "$archive/project-subdomains.conf" "$subdomains"
        exit 1
    fi
    sudo systemctl reload nginx
fi
export XDG_RUNTIME_DIR=/run/user/1000
if [ -f /home/ubuntu/.config/systemd/user/daily-english.service ]; then
    cp -p /home/ubuntu/.config/systemd/user/daily-english.service "$archive/"
    systemctl --user disable --now daily-english.service
    mv /home/ubuntu/.config/systemd/user/daily-english.service "$archive/daily-english.service.disabled"
    systemctl --user daemon-reload
fi
if [ -f /etc/systemd/system/life-list.service ]; then
    sudo cp -p /etc/systemd/system/life-list.service "$archive/"
    sudo systemctl disable --now life-list.service
    sudo mv /etc/systemd/system/life-list.service "$archive/life-list.service.disabled"
    sudo systemctl daemon-reload
fi
for name in daily-english-web life-list; do
    target="/home/ubuntu/$name"
    # Verify the exact source; do not follow a symlink to an unrelated checkout.
    if [ -e "$target" ]; then
        [ ! -L "$target" ] && [ "$(readlink -f "$target")" = "$target" ]
        [ ! -e "$archive/$name" ]
        mv -- "$target" "$archive/$name"
    fi
done
if ss -ltnH '( sport = :8080 or sport = :5002 )' | grep -q .; then
    echo "An obsolete port is still listening; inspect it before completing retirement" >&2
    exit 1
fi
date -u +%FT%TZ > "$archive/finished"
echo "Retired daily-english and life-list; private recovery archive: $archive"
