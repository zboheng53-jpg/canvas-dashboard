#!/usr/bin/env bash
# One-time setup for GitHub Actions deployments. Run as root on the production
# host, from a checkout that contains deploy/github-deploy/.
#
#   sudo bash deploy/github-deploy/setup-deploy-user.sh <authorized_keys-file>
#
# <authorized_keys-file> contains the public key(s) of the GitHub Actions deploy
# key. The matching private key belongs in the `production` environment secret
# DEPLOY_SSH_KEY; never commit it or paste it into a terminal that logs.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
key_file=${1:-}

[ "$(id -u)" -eq 0 ] || { echo "Run this script as root." >&2; exit 1; }
[ -n "$key_file" ] && [ -f "$key_file" ] || {
    echo "Usage: sudo bash $0 <authorized_keys-file>" >&2
    exit 1
}
command -v visudo >/dev/null || { echo "visudo is required." >&2; exit 1; }
[ -f "$script_dir/canvas-deploy" ] || {
    echo "canvas-deploy is missing next to this script." >&2
    exit 1
}

if ! id deploy >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash --comment "GitHub Actions deployment" deploy
fi
passwd -l deploy >/dev/null

install -d -m 0750 -o deploy -g deploy /home/deploy
install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh /home/deploy/incoming
install -m 0600 -o deploy -g deploy "$key_file" /home/deploy/.ssh/authorized_keys

install -o root -g root -m 0755 "$script_dir/canvas-deploy" /usr/local/sbin/canvas-deploy

sudoers_file=$(mktemp)
trap 'rm -f -- "$sudoers_file"' EXIT
cat > "$sudoers_file" <<'EOF'
# The GitHub Actions deploy user may only run the root-owned deployment wrapper.
deploy ALL=(root) NOPASSWD: /usr/local/sbin/canvas-deploy
EOF
chmod 0440 "$sudoers_file"
visudo -cf "$sudoers_file" >/dev/null
install -o root -g root -m 0440 "$sudoers_file" /etc/sudoers.d/canvas-deploy

install -d -o ubuntu -g ubuntu -m 0755 /home/ubuntu/canvas-dashboard/incoming

echo "deploy user is ready."
echo "Verify from the workstation that holds the private key:"
echo "  ssh -i <deploy-key> deploy@<host> 'sudo /usr/local/sbin/canvas-deploy status'"
echo "Then store the private key as the DEPLOY_SSH_KEY environment secret."
