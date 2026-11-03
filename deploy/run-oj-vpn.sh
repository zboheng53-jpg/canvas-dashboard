#!/usr/bin/env bash
set -euo pipefail
network=canvas-dashboard-oj-vpn
name=canvas-dashboard-oj-vpn
credential="${CREDENTIALS_DIRECTORY:?systemd credentials are required}/oj-vpn"
test -r "$credential"
if docker network inspect "$network" >/dev/null 2>&1; then
    test "$(docker network inspect -f '{{index .Labels "io.canvas-dashboard.owner"}}' "$network")" = oj-vpn
else
    docker network create --label io.canvas-dashboard.owner=oj-vpn "$network" >/dev/null
fi
if docker container inspect "$name" >/dev/null 2>&1; then
    test "$(docker container inspect -f '{{index .Config.Labels "io.canvas-dashboard.owner"}}' "$name")" = oj-vpn
    docker container rm -f "$name" >/dev/null
fi
exec docker run --rm -i --name "$name" --label io.canvas-dashboard.owner=oj-vpn \
    --network "$network" --cap-add NET_ADMIN --device /dev/net/tun \
    --security-opt no-new-privileges --pids-limit 128 --memory 512m \
    --publish 127.0.0.1:18080:18080 \
    "${OJ_VPN_IMAGE:-canvas-dashboard-oj-vpn:latest}" < "$credential"
