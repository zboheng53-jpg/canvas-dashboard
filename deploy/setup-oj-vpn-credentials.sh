#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
test "$(id -u)" = 0 || { echo 'Run this script with sudo in an interactive terminal.'; exit 1; }
test -t 0 || { echo 'An interactive terminal is required.'; exit 1; }
root=/home/ubuntu/canvas-dashboard/current
if [ "${1:-}" != "--credential-only" ]; then
    test -f "$root/deploy/canvas-dashboard-oj-vpn.service"
fi
read -r -p 'VPN 学号: ' account </dev/tty
read -r -s -p 'VPN 密码: ' password </dev/tty
printf '\n' >/dev/tty
test -n "$account" && test -n "$password" || { echo '账号和密码不能为空'; exit 1; }
test -d /etc/canvas-dashboard
tmp=$(mktemp /etc/canvas-dashboard/.oj-vpn-cred.XXXXXXXX)
trap 'rm -f -- "$tmp"; unset password' EXIT
printf '%s\n%s\n' "$account" "$password" |
    python3 -c 'import json,sys; a=sys.stdin.readline().rstrip("\n"); p=sys.stdin.readline().rstrip("\n"); json.dump({"username":a,"password":p},sys.stdout,ensure_ascii=False)' |
    systemd-creds encrypt --name=oj-vpn --with-key=host - - > "$tmp"
unset password
chmod 0600 "$tmp"
mv -f -- "$tmp" /etc/canvas-dashboard/oj-vpn.cred
trap - EXIT
if [ "${1:-}" = "--credential-only" ]; then
    echo '加密 VPN 凭据已保存。'
    exit 0
fi
docker image inspect canvas-dashboard-oj-vpn:latest >/dev/null
install -m 0644 "$root/deploy/canvas-dashboard-oj-vpn.service" /etc/systemd/system/canvas-dashboard-oj-vpn.service
systemctl daemon-reload
systemctl enable --now canvas-dashboard-oj-vpn.service
echo 'VPN 服务已启动；请返回聊天确认连接状态。'
