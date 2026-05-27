#!/usr/bin/env bash
set -euo pipefail

TARGET=${1:-hp4}
REMOTE_PATH=${2:-/tmp/ksp-control-panel.tar.gz}

cd "$(dirname "$0")/.."

bash deploy/package-for-ubuntu.sh
scp deploy/dist/ksp-control-panel.tar.gz "$TARGET:$REMOTE_PATH"

echo "Sent deploy package to $TARGET:$REMOTE_PATH"
