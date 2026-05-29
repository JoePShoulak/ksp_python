#!/usr/bin/env bash
set -euo pipefail

TARGET=${1:-hp1}
REMOTE_PATH=${2:-/tmp/ksp-control-panel.tar.gz}

cd "$(dirname "$0")/.."

SSH_CONFIG="deploy/dist/ksp-ssh-config"

ensure_ssh_config() {
  mkdir -p "$(dirname "$SSH_CONFIG")"
  cat > "$SSH_CONFIG" <<EOF
Host hp1
  HostName 192.168.20.21
  User leo
  StrictHostKeyChecking accept-new

Host hp4
  HostName 192.168.20.24
  User leo
  StrictHostKeyChecking accept-new

Host *
  StrictHostKeyChecking accept-new
EOF
}

bash deploy/package-for-ubuntu.sh
ensure_ssh_config
scp -F "$SSH_CONFIG" deploy/dist/ksp-control-panel.tar.gz "$TARGET:$REMOTE_PATH"

echo "Sent deploy package to $TARGET:$REMOTE_PATH"

