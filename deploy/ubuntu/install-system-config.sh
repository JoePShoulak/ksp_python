#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ksp-control-panel/app}"
DEPLOY_USER="${DEPLOY_USER:-ksp}"

install -m 0644 "$APP_DIR/deploy/ubuntu/ksp-backend.service" /etc/systemd/system/ksp-backend.service
install -m 0644 "$APP_DIR/deploy/ubuntu/ksp-control-panel.nginx" /etc/nginx/sites-available/ksp-control-panel
ln -sfn /etc/nginx/sites-available/ksp-control-panel /etc/nginx/sites-enabled/ksp-control-panel
rm -f /etc/nginx/sites-enabled/default

cat >/etc/sudoers.d/ksp-control-panel-deploy <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/ksp-control-panel-install-system-config, /bin/systemctl start ksp-backend, /bin/systemctl stop ksp-backend, /bin/systemctl restart ksp-backend, /bin/systemctl reload nginx, /usr/bin/systemctl start ksp-backend, /usr/bin/systemctl stop ksp-backend, /usr/bin/systemctl restart ksp-backend, /usr/bin/systemctl reload nginx, /usr/sbin/nginx -t, /bin/journalctl -u ksp-backend -n 120 -f, /usr/bin/journalctl -u ksp-backend -n 120 -f
EOF
chmod 0440 /etc/sudoers.d/ksp-control-panel-deploy

systemctl daemon-reload
systemctl enable ksp-backend >/dev/null
nginx -t
systemctl reload nginx || systemctl restart nginx
