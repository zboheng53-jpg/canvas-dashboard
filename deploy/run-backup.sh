#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/canvas-dashboard
backup_tool="$root/current/scripts/backup_data.py"
if [ ! -f "$backup_tool" ]; then
    backup_tool="$root/incoming/backup_data.py"
fi
stopped=0

finish() {
    status=$?
    trap - EXIT
    if [ "$stopped" -eq 1 ]; then
        systemctl start canvas-dashboard.service zhihuishu-worker.service || status=1
        healthy=0
        for attempt in $(seq 1 20); do
            if curl -fsS --max-time 5 http://127.0.0.1:5000/healthz >/dev/null 2>&1; then
                healthy=1
                break
            fi
            sleep 1
        done
        if [ "$healthy" -ne 1 ]; then
            echo "Services did not become healthy after backup" >&2
            status=1
        fi
    fi
    exit "$status"
}
trap finish EXIT

systemctl stop canvas-dashboard.service zhihuishu-worker.service
stopped=1
install -d -o ubuntu -g ubuntu -m 0700 "$root/backups"
runuser -u ubuntu -- "$root/.venv/bin/python" \
    "$backup_tool" create \
    --data-dir "$root/data" \
    --output-dir "$root/backups" \
    --public-key /etc/canvas-dashboard/backup-public.pem \
    --retention 14
