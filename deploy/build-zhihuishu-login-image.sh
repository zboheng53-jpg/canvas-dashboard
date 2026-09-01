#!/usr/bin/env bash
set -euo pipefail

IMAGE_TAG="${IMAGE_TAG:-canvas-dashboard-zhihuishu-login:latest}"
ROOTFS_DIR="${ROOTFS_DIR:-/tmp/zhihuishu-login-rootfs}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://mirrors.tencentyun.com/debian}"
DEBIAN_SUITE="${DEBIAN_SUITE:-bookworm}"
IMAGE_CONTEXT_LABEL="io.canvas-dashboard.zhihuishu-login.context-sha256"
IMAGE_BASE_CONTEXT_VERSION="debian-bookworm-chromium-v1"

# Keep the expensive Chromium rootfs build tied to its actual inputs.  This
# image is shared by every immutable application release, so rebuilding it for
# a CSS/JS-only deploy is pure cost and can temporarily require several GB.
image_context_hash() {
  {
    local file
    for file in \
      deploy/zhihuishu-login-browser-entrypoint.sh
    do
      printf '%s\0' "$file"
      cat "$file"
      printf '\0'
    done
    printf '%s\0' "$IMAGE_BASE_CONTEXT_VERSION"
  } | sha256sum | awk '{print $1}'
}

CONTEXT_HASH="$(image_context_hash)"
# The production image predates fingerprint labels but was built from this
# exact context.  Accept it once; any later source change forces a rebuild and
# writes the label below.
LEGACY_CONTEXT_HASH="0dbc537b5c8194e2e3b2e72f2c52127eed65fb7ef240252aa85f547ecc6af6b8"
EXISTING_CONTEXT_HASH="$(sudo docker image inspect --format "{{ index .Config.Labels \"$IMAGE_CONTEXT_LABEL\" }}" "$IMAGE_TAG" 2>/dev/null || true)"

if [ "$EXISTING_CONTEXT_HASH" = "$CONTEXT_HASH" ] || \
   { [ -z "$EXISTING_CONTEXT_HASH" ] && [ "$CONTEXT_HASH" = "$LEGACY_CONTEXT_HASH" ] && sudo docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; }; then
  echo "Reusing existing Zhihuishu login image for context $CONTEXT_HASH"
  exit 0
fi

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

PACKAGES="bash,ca-certificates,chromium,dbus,dbus-x11,fonts-noto-cjk,novnc,openbox,procps,python3-cffi-backend,socat,websockify,x11vnc,xvfb"

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
  --change "LABEL $IMAGE_CONTEXT_LABEL=$CONTEXT_HASH" \
  - "$IMAGE_TAG"

sudo rm -rf "$ROOTFS_DIR"
sudo docker image inspect "$IMAGE_TAG" >/dev/null
sudo docker images "$IMAGE_TAG"
