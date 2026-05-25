#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-ksp-control-panel}"
DEPLOY_USER="${DEPLOY_USER:-ksp}"
APP_ROOT="${APP_ROOT:-/opt/$APP_NAME}"
APP_DIR="${APP_DIR:-$APP_ROOT/app}"
BARE_REPO="${BARE_REPO:-/srv/git/$APP_NAME.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
ENV_FILE="${ENV_FILE:-/etc/$APP_NAME.env}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

apt-get update
apt-get install -y ca-certificates curl git nginx python3 python3-pip python3-venv rsync sudo

if ! command -v node >/dev/null 2>&1 || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi

install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_ROOT" "$APP_DIR" "$(dirname "$BARE_REPO")"

if [[ ! -d "$BARE_REPO" ]]; then
  sudo -u "$DEPLOY_USER" git init --bare "$BARE_REPO"
fi

install -m 0755 "$SCRIPT_DIR/git-post-receive" "$BARE_REPO/hooks/post-receive"
chown "$DEPLOY_USER:$DEPLOY_USER" "$BARE_REPO/hooks/post-receive"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0644 "$SCRIPT_DIR/env.example" "$ENV_FILE"
fi

install -m 0644 "$SCRIPT_DIR/ksp-backend.service" /etc/systemd/system/ksp-backend.service
install -m 0644 "$SCRIPT_DIR/ksp-control-panel.nginx" /etc/nginx/sites-available/ksp-control-panel
ln -sfn /etc/nginx/sites-available/ksp-control-panel /etc/nginx/sites-enabled/ksp-control-panel
rm -f /etc/nginx/sites-enabled/default

cat >/etc/sudoers.d/ksp-control-panel-deploy <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /bin/systemctl restart ksp-backend, /bin/systemctl reload nginx, /usr/bin/systemctl restart ksp-backend, /usr/bin/systemctl reload nginx, /usr/sbin/nginx -t
EOF
chmod 0440 /etc/sudoers.d/ksp-control-panel-deploy

systemctl daemon-reload
systemctl enable ksp-backend
nginx -t
systemctl reload nginx || systemctl restart nginx

if [[ -d "$REPO_DIR/.git" ]]; then
  rsync -a --delete \
    --exclude .git \
    --exclude frontend/node_modules \
    --exclude frontend/dist \
    --exclude __pycache__ \
    "$REPO_DIR/" "$APP_DIR/"
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_ROOT"
  sudo -u "$DEPLOY_USER" bash "$APP_DIR/deploy/ubuntu/deploy.sh"
fi

cat <<EOF

Bootstrap complete.

Production URL:
  http://$(hostname -I | awk '{print $1}'):5173

Push-to-deploy remote:
  ssh://$DEPLOY_USER@$(hostname -I | awk '{print $1}')$BARE_REPO

Expected branch:
  $DEPLOY_BRANCH

Edit production config:
  sudo nano $ENV_FILE
EOF
