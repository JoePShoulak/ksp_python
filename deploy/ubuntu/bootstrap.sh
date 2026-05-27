#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-ksp-control-panel}"
DEPLOY_USER="${DEPLOY_USER:-ksp}"
DEPLOY_OPERATOR="${DEPLOY_OPERATOR:-leo}"
APP_ROOT="${APP_ROOT:-/opt/$APP_NAME}"
APP_DIR="${APP_DIR:-$APP_ROOT/app}"
ENV_FILE="${ENV_FILE:-/etc/$APP_NAME.env}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

apt-get update
apt-get install -y ca-certificates curl nginx python3 python3-pip python3-venv sudo

if ! command -v node >/dev/null 2>&1 || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi

install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_ROOT" "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0644 "$SCRIPT_DIR/env.example" "$ENV_FILE"
fi

install -m 0755 "$SCRIPT_DIR/install-system-config.sh" /usr/local/sbin/ksp-control-panel-install-system-config
install -m 0755 "$SCRIPT_DIR/ksp-control-panel-apply-deploy" /usr/local/sbin/ksp-control-panel-apply-deploy

cat >/etc/sudoers.d/ksp-control-panel-deploy <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/ksp-control-panel-install-system-config, /bin/systemctl start ksp-backend, /bin/systemctl stop ksp-backend, /bin/systemctl restart ksp-backend, /bin/systemctl reload nginx, /usr/bin/systemctl start ksp-backend, /usr/bin/systemctl stop ksp-backend, /usr/bin/systemctl restart ksp-backend, /usr/bin/systemctl reload nginx, /usr/sbin/nginx -t, /bin/journalctl -u ksp-backend -n 120 -f, /usr/bin/journalctl -u ksp-backend -n 120 -f
$DEPLOY_OPERATOR ALL=(root) NOPASSWD: /usr/local/sbin/ksp-control-panel-apply-deploy /tmp/ksp-control-panel.tar.gz
$DEPLOY_OPERATOR ALL=(root) NOPASSWD: /bin/systemctl start ksp-backend, /bin/systemctl stop ksp-backend, /bin/systemctl restart ksp-backend, /bin/systemctl reload nginx, /usr/bin/systemctl start ksp-backend, /usr/bin/systemctl stop ksp-backend, /usr/bin/systemctl restart ksp-backend, /usr/bin/systemctl reload nginx, /usr/sbin/nginx -t
EOF
visudo -cf /etc/sudoers.d/ksp-control-panel-deploy
chmod 0440 /etc/sudoers.d/ksp-control-panel-deploy

cat <<EOF

Bootstrap complete.

Production URL:
  http://$(hostname -I | awk '{print $1}'):5173

Deploy from the dev machine with:
  cd C:/Users/joeps/coding/ksp_python
  source deploy/aliases.sh
  deploy

After this bootstrap has installed /usr/local/sbin/ksp-control-panel-apply-deploy
and /etc/sudoers.d/ksp-control-panel-deploy, normal deploys can run without a
sudo password prompt:
  deploy

Edit production config:
  sudo nano $ENV_FILE
EOF
