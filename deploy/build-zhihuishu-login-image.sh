#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-canvas-dashboard-zhihuishu-login:latest}"
ROOTFS_DIR="${ROOTFS_DIR:-/tmp/zhihuishu-login-rootfs}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://mirrors.tencentyun.com/debian}"
DEBIAN_SUITE="${DEBIAN_SUITE:-bookworm}"

case "$ROOTFS_DIR" in
  /tmp/zhihuishu-login-rootfs*) ;;
  *)
    echo "Refusing to remove unexpected ROOTFS_DIR: $ROOTFS_DIR" >&2
    exit 1
    ;;
esac

if ! command -v debootstrap >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y debootstrap
fi

sudo rm -rf "$ROOTFS_DIR"

PACKAGES="bash,ca-certificates,chromium,dbus,dbus-x11,fonts-noto-cjk,novnc,openbox,procps,python3-cffi-backend,websockify,x11vnc,xvfb"

sudo debootstrap \
  --variant=minbase \
  --include="$PACKAGES" \
  "$DEBIAN_SUITE" \
  "$ROOTFS_DIR" \
  "$DEBIAN_MIRROR"

sudo install -m 0755 \
  deploy/zhihuishu-login-browser-entrypoint.sh \
  "$ROOTFS_DIR/usr/local/bin/zhihuishu-login-browser"
sudo mkdir -p "$ROOTFS_DIR/tmp/.X11-unix"
sudo chmod 1777 "$ROOTFS_DIR/tmp" "$ROOTFS_DIR/tmp/.X11-unix"

sudo tar -C "$ROOTFS_DIR" --numeric-owner -c . | sudo docker import \
  --change 'ENV DISPLAY=:99' \
  --change 'EXPOSE 6080' \
  --change 'ENTRYPOINT ["/usr/local/bin/zhihuishu-login-browser"]' \
  - "$IMAGE_TAG"

sudo rm -rf "$ROOTFS_DIR"
sudo docker image inspect "$IMAGE_TAG" >/dev/null
sudo docker images "$IMAGE_TAG"
