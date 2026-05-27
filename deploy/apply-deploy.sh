#!/usr/bin/env bash
set -euo pipefail

ARCHIVE=${1:-/tmp/ksp-control-panel.tar.gz}
APP_NAME="${APP_NAME:-ksp-control-panel}"
DEPLOY_USER="${DEPLOY_USER:-ksp}"
APP_ROOT="${APP_ROOT:-/opt/$APP_NAME}"
APP_DIR="${APP_DIR:-$APP_ROOT/app}"

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi

sudo install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_ROOT" "$APP_DIR"
sudo find "$APP_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
sudo tar -xzf "$ARCHIVE" -C "$APP_DIR"
sudo chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT"

sudo -u "$DEPLOY_USER" bash -lc "cd '$APP_DIR' && bash deploy/ubuntu/deploy.sh"
