#!/usr/bin/env bash
set -euo pipefail

SERVER=""
TOKEN=""
TARGET="agents"
INSTALL_DIR=""
MIGRATE_LEGACY=0

usage() {
  cat <<'EOF'
Usage:
  install.sh --server <url> --token <token> [--target <agents|claude>] [--migrate-legacy]
  install.sh --dir <path> [--server <url>] [--token <token>]

Options:
  --server <url>       Canvas Dashboard base URL (e.g. http://127.0.0.1:5000)
  --token <token>      Canvas Dashboard Agent API Token (cda_...)
  --target <target>    Install target: 'agents' (~/.agents/skills/canvas-dashboard)
                       or 'claude' (agents dir + ~/.claude/skills symlink). Default: agents
  --dir <path>         Custom installation directory
  --migrate-legacy     Migrate legacy installation copies
  -h, --help           Show this help message
EOF
}

fail() {
  echo "[ERR] $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server)
      SERVER="${2:-}"
      shift 2 || fail "Missing value for --server"
      ;;
    --token)
      TOKEN="${2:-}"
      shift 2 || fail "Missing value for --token"
      ;;
    --target)
      TARGET="${2:-}"
      shift 2 || fail "Missing value for --target"
      ;;
    --dir)
      INSTALL_DIR="${2:-}"
      shift 2 || fail "Missing value for --dir"
      ;;
    --migrate-legacy)
      MIGRATE_LEGACY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ -z "$INSTALL_DIR" ]]; then
  case "$TARGET" in
    agents|claude)
      INSTALL_DIR="$HOME/.agents/skills/canvas-dashboard"
      ;;
    *)
      fail "Invalid target: $TARGET. Must be 'agents' or 'claude'"
      ;;
  esac
fi

if [[ -z "$SERVER" ]]; then
  SERVER="http://127.0.0.1:5000"
fi
SERVER="${SERVER%/}"

# Temporary staging directory
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/canvas-skill-XXXXXX")"
trap 'rm -rf -- "$TMP_DIR"' EXIT

echo "==> Downloading Canvas Dashboard Skill files from $SERVER ..."

# Download SKILL.md
if ! curl -fsSL "$SERVER/skill/SKILL.md" -o "$TMP_DIR/SKILL.md"; then
  fail "Failed to download SKILL.md from $SERVER/skill/SKILL.md"
fi

# Download canvas_api.py
if ! curl -fsSL "$SERVER/skill/canvas_api.py" -o "$TMP_DIR/canvas_api.py"; then
  fail "Failed to download canvas_api.py from $SERVER/skill/canvas_api.py"
fi

# Determine token: use passed token, or inherit from existing config if updating
EXISTING_CONFIG="$INSTALL_DIR/config.json"
FINAL_TOKEN="$TOKEN"
if [[ -z "$FINAL_TOKEN" && -f "$EXISTING_CONFIG" ]]; then
  FINAL_TOKEN="$(grep -o '"token": *"[^"]*"' "$EXISTING_CONFIG" | head -n1 | cut -d'"' -f4 || true)"
fi

# Write config.json
cat > "$TMP_DIR/config.json" <<EOF
{
  "server_url": "$SERVER",
  "token": "$FINAL_TOKEN"
}
EOF
chmod 0600 "$TMP_DIR/config.json" 2>/dev/null || true

# Write .gitignore
cat > "$TMP_DIR/.gitignore" <<'EOF'
config.json
.env
*.tmp
__pycache__/
EOF

# Install files to destination
mkdir -p "$(dirname "$INSTALL_DIR")"

if [[ -d "$INSTALL_DIR" ]]; then
  echo "==> Updating existing Skill at $INSTALL_DIR ..."
else
  echo "==> Installing Canvas Dashboard Skill to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"
fi

cp -f "$TMP_DIR/SKILL.md" "$INSTALL_DIR/SKILL.md"
cp -f "$TMP_DIR/canvas_api.py" "$INSTALL_DIR/canvas_api.py"
cp -f "$TMP_DIR/config.json" "$INSTALL_DIR/config.json"
cp -f "$TMP_DIR/.gitignore" "$INSTALL_DIR/.gitignore"
chmod 0600 "$INSTALL_DIR/config.json" 2>/dev/null || true

# Handle Claude Code symlink if requested
if [[ "$TARGET" == "claude" ]]; then
  CLAUDE_DIR="$HOME/.claude/skills"
  CLAUDE_TARGET="$CLAUDE_DIR/canvas-dashboard"
  mkdir -p "$CLAUDE_DIR"
  if [[ -L "$CLAUDE_TARGET" ]]; then
    rm -f "$CLAUDE_TARGET"
  elif [[ -d "$CLAUDE_TARGET" && "$MIGRATE_LEGACY" -eq 1 ]]; then
    rm -rf "$CLAUDE_TARGET"
  fi
  if [[ ! -e "$CLAUDE_TARGET" ]]; then
    ln -s "$INSTALL_DIR" "$CLAUDE_TARGET"
    echo "==> Created Claude Code symlink: $CLAUDE_TARGET -> $INSTALL_DIR"
  fi
fi

echo "==> Canvas Dashboard Skill installed successfully!"
echo "    Path: $INSTALL_DIR"
if [[ -z "$FINAL_TOKEN" ]]; then
  echo "    [NOTE] Token not configured. Please add your token into $INSTALL_DIR/config.json"
fi
echo ""
echo "Next steps:"
echo "1. Restart your Agent or start a new session (most agents discover skills at startup)."
echo "2. Verify by asking: '我今天有什么课？分别在哪个教室？'"
