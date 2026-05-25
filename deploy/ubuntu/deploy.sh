#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ksp-control-panel/app}"
APP_ROOT="${APP_ROOT:-/opt/ksp-control-panel}"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
BACKEND_SERVICE="${BACKEND_SERVICE:-ksp-backend}"

cd "$APP_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r backend/requirements.txt
"$VENV_DIR/bin/python" -m py_compile backend/main.py backend/telemetry.py backend/krpc_utils.py

cd "$APP_DIR/frontend"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build

sudo systemctl restart "$BACKEND_SERVICE"
sudo nginx -t
sudo systemctl reload nginx
