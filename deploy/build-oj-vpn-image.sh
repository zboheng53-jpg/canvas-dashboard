#!/usr/bin/env bash
set -euo pipefail
root=/home/ubuntu/canvas-dashboard
vendor="$root/vendor/motionpro-linux-1.2.20.sh"
expected=fdcaf0510c5ef6c0ac866c8c0e13b2225db244e7f85e3d291273009b7f7582f3
url=https://support.arraynetworks.net/prx/001/http/supportportal.arraynetworks.net/downloads/pkg_9_4_5_13/MP_Linux-1.2.20-cr2025/MotionPro_Linux_Ubuntu_x64.sh
source_root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d /tmp/canvas-oj-vpn-build-XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
if [ -f "$vendor" ]; then
    cp "$vendor" "$work/motionpro.sh"
else
    curl -fLsS --retry 2 --connect-timeout 15 --max-time 600 "$url" -o "$work/motionpro.sh"
fi
printf '%s  %s\n' "$expected" "$work/motionpro.sh" | sha256sum -c -
cp "$source_root/deploy/oj-vpn.Dockerfile" "$work/Dockerfile"
cp "$source_root/deploy/oj_vpn_gateway.py" "$source_root/deploy/oj_vpn_supervisor.py" "$work/"
base=$(docker image inspect --format '{{.Id}}' canvas-dashboard-zhihuishu-login:latest)
docker build --build-arg "BASE_IMAGE=$base" -t canvas-dashboard-oj-vpn:latest "$work"
