#!/usr/bin/env bash
set -euo pipefail

LOGIN_URL="${LOGIN_URL:-${ZHIHUISHU_LOGIN_URL:-https://passport.zhihuishu.com/login}}"
PROFILE_DIR="${CHROME_PROFILE_DIR:-/profile}"
DISPLAY="${DISPLAY:-:99}"

export DISPLAY
mkdir -p "$PROFILE_DIR"
export HOME="$PROFILE_DIR/home"
export XDG_CONFIG_HOME="$PROFILE_DIR/.config"
export XDG_CACHE_HOME="$PROFILE_DIR/.cache"
export XDG_RUNTIME_DIR="$PROFILE_DIR/.runtime"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

lock_target="$(readlink "$PROFILE_DIR/SingletonLock" 2>/dev/null || true)"
if [ -n "$lock_target" ]; then
  current_host="$(hostname)"
  should_remove_lock=1
  if [ "${lock_target#"$current_host"-}" != "$lock_target" ]; then
    lock_pid="${lock_target#"$current_host"-}"
    if kill -0 "$lock_pid" >/dev/null 2>&1; then
      should_remove_lock=0
    fi
  fi
  if [ "$should_remove_lock" -eq 1 ]; then
    rm -f "$PROFILE_DIR/SingletonLock" "$PROFILE_DIR/SingletonSocket" "$PROFILE_DIR/SingletonCookie"
  fi
fi

Xvfb "$DISPLAY" -screen 0 1280x900x24 -nolisten tcp &
openbox >/tmp/openbox.log 2>&1 &
x11vnc -display "$DISPLAY" -forever -shared -nopw -listen 127.0.0.1 -xkb >/tmp/x11vnc.log 2>&1 &
websockify --web=/usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &

CHROME_BIN="${CHROME_BIN:-}"
if [ -z "$CHROME_BIN" ]; then
  if [ -d /ms-playwright ]; then
    CHROME_BIN="$(find /ms-playwright -path '*/chrome-linux/chrome' | head -n 1)"
  fi
fi

if [ -z "$CHROME_BIN" ]; then
  if [ -x /usr/lib/chromium/chromium ]; then
    CHROME_BIN="/usr/lib/chromium/chromium"
  fi
fi

if [ -z "$CHROME_BIN" ]; then
  for candidate in chromium chromium-browser google-chrome chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
      CHROME_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi

if [ -z "$CHROME_BIN" ]; then
  echo "No Chromium or Chrome binary found" >&2
  exit 1
fi

"$CHROME_BIN" \
  --no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-crash-reporter \
  --disable-crashpad \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$PROFILE_DIR" \
  --window-size=1280,900 \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port="${CHROME_REMOTE_DEBUGGING_PORT:-9222}" \
  "$LOGIN_URL" >/tmp/chromium.log 2>&1 &

wait -n
