#!/usr/bin/env bash
set -euo pipefail

root=/home/ubuntu/canvas-dashboard
archive=${1:?archive path is required}
release_name=${2:?release name is required}
releases="$root/releases"
release="$releases/$release_name"
release_retention=5

case "$release_name" in
    *[!A-Za-z0-9._-]*|"") echo "Invalid release name" >&2; exit 2 ;;
esac
case "$archive" in
    "$root"/incoming/*.tar.gz) ;;
    *) echo "Archive must be under $root/incoming" >&2; exit 2 ;;
esac

install_configs() {
    local source=$1
    for unit in \
        canvas-dashboard.service \
        zhihuishu-worker.service \
        zhihuishu-login-cleanup.service \
        zhihuishu-login-cleanup.timer \
        canvas-dashboard-backup.service \
        canvas-dashboard-backup.timer
    do
        if [ -f "$source/deploy/$unit" ]; then
            sudo install -m 0644 "$source/deploy/$unit" "/etc/systemd/system/$unit" || return
        fi
    done
    local nginx_source="$source/deploy/canvas-dashboard.nginx"
    if sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem &&
       [ -f "$source/deploy/canvas-dashboard.https.nginx" ]; then
        nginx_source="$source/deploy/canvas-dashboard.https.nginx"
    fi
    sudo install -m 0644 "$nginx_source" /etc/nginx/sites-enabled/canvas-dashboard || return
    sudo systemctl daemon-reload || return
    sudo nginx -t || return
}

build_browser_login_image() {
    local source=$1
    sudo docker build \
        -f "$source/deploy/zhihuishu-login-browser.Dockerfile" \
        -t canvas-dashboard-zhihuishu-login:latest \
        "$source" || return
}

activate_release() {
    local target=$1
    ln -sfn "$target" "$root/current.next" || return
    mv -Tf "$root/current.next" "$root/current" || return
    install_configs "$target" || return
    sudo systemctl enable canvas-dashboard.service zhihuishu-worker.service || return
    sudo systemctl enable --now zhihuishu-login-cleanup.timer canvas-dashboard-backup.timer || return
    sudo systemctl restart canvas-dashboard.service zhihuishu-worker.service || return
    sudo systemctl reload nginx || return
}

prune_old_releases() {
    local active rollback name candidate resolved
    local seen=0
    local removed=0

    active=$(readlink -f "$root/current") || return
    rollback=$(cat "$root/.previous-release") || return

    while IFS= read -r name; do
        case "$name" in
            release-*|legacy-*) ;;
            *) continue ;;
        esac

        candidate="$releases/$name"
        resolved=$(readlink -f "$candidate") || return
        case "$resolved" in
            "$releases"/*) ;;
            *) echo "Refusing unsafe release cleanup target: $resolved" >&2; return 1 ;;
        esac

        seen=$((seen + 1))
        if [ "$seen" -le "$release_retention" ] ||
           [ "$resolved" = "$active" ] ||
           [ "$resolved" = "$rollback" ]; then
            continue
        fi

        rm -rf -- "$candidate"
        removed=$((removed + 1))
    done < <(find "$releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)

    echo "Pruned $removed old release(s); retained the newest $release_retention plus active rollback targets"
}

mkdir -p "$releases" "$root/incoming"
if [ ! -d "$release" ]; then
    mkdir "$release"
    tar -xzf "$archive" -C "$release"
fi
test -f "$release/app.py"
test -f "$release/deploy/canvas-dashboard.nginx"
test -f "$release/deploy/canvas-dashboard.service"
test -f /etc/canvas-dashboard/backup-public.pem
ln -s "$root/data" "$release/data"
ln -s "$root/.venv" "$release/.venv"

if [ -L "$root/current" ]; then
    previous=$(readlink -f "$root/current")
else
    legacy="$releases/legacy-$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir "$legacy"
    tar -C "$root" \
        --exclude='./data' \
        --exclude='./.venv' \
        --exclude='./releases' \
        --exclude='./incoming' \
        --exclude='./backups' \
        --exclude='./current' \
        -cf - . | tar -xf - -C "$legacy"
    mkdir -p "$legacy/deploy" "$legacy/scripts"
    cp "$release/scripts/backup_data.py" "$legacy/scripts/backup_data.py"
    cp "$release/deploy/"*.service "$release/deploy/"*.timer "$release/deploy/run-backup.sh" "$legacy/deploy/"
    cp "$release/deploy/canvas-dashboard.https.nginx" "$legacy/deploy/"
    sudo cp /etc/nginx/sites-enabled/canvas-dashboard "$legacy/deploy/canvas-dashboard.nginx"
    sudo chown ubuntu:ubuntu "$legacy/deploy/canvas-dashboard.nginx"
    ln -s "$root/data" "$legacy/data"
    ln -s "$root/.venv" "$legacy/.venv"
    previous="$legacy"
fi

case "$previous" in
    "$releases"/*) ;;
    *) echo "Refusing unsafe previous release: $previous" >&2; exit 2 ;;
esac
printf '%s\n' "$previous" > "$root/.previous-release"

if ! build_browser_login_image "$release"; then
    echo "Browser login image build failed; release was not activated" >&2
    exit 1
fi

if ! activate_release "$release"; then
    echo "Release activation failed; restoring $previous" >&2
    activate_release "$previous" || true
    exit 1
fi

for attempt in $(seq 1 20); do
    if curl -fsS --max-time 5 http://127.0.0.1:5000/healthz >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 20 ]; then
        echo "Health check failed; restoring $previous" >&2
        activate_release "$previous" || true
        exit 1
    fi
    sleep 1
done

if sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem; then
    curl -fsS --max-time 10 \
        --resolve canvas-dashboard.xyz:443:127.0.0.1 \
        https://canvas-dashboard.xyz/healthz >/dev/null
fi

systemctl is-active --quiet canvas-dashboard.service
systemctl is-active --quiet zhihuishu-worker.service
systemctl is-active --quiet zhihuishu-login-cleanup.timer
systemctl is-active --quiet canvas-dashboard-backup.timer
if ! prune_old_releases; then
    echo "Warning: release activation succeeded, but old release cleanup failed" >&2
fi
rm -f "$archive"
echo "Activated release $release_name"
