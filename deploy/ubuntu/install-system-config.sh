#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ksp-control-panel/app}"
DEPLOY_USER="${DEPLOY_USER:-ksp}"
DEPLOY_OPERATOR="${DEPLOY_OPERATOR:-leo}"

install -m 0644 "$APP_DIR/deploy/ubuntu/ksp-backend.service" /etc/systemd/system/ksp-backend.service
install -m 0644 "$APP_DIR/deploy/ubuntu/ksp-control-panel.nginx" /etc/nginx/sites-available/ksp-control-panel
install -m 0755 "$APP_DIR/deploy/ubuntu/ksp-control-panel-apply-deploy" /usr/local/sbin/ksp-control-panel-apply-deploy
ln -sfn /etc/nginx/sites-available/ksp-control-panel /etc/nginx/sites-enabled/ksp-control-panel
rm -f /etc/nginx/sites-enabled/default

cat >/etc/sudoers.d/ksp-control-panel-deploy <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/ksp-control-panel-install-system-config, /bin/systemctl start ksp-backend, /bin/systemctl stop ksp-backend, /bin/systemctl restart ksp-backend, /bin/systemctl reload nginx, /usr/bin/systemctl start ksp-backend, /usr/bin/systemctl stop ksp-backend, /usr/bin/systemctl restart ksp-backend, /usr/bin/systemctl reload nginx, /usr/sbin/nginx -t, /bin/journalctl -u ksp-backend -n 120 -f, /usr/bin/journalctl -u ksp-backend -n 120 -f
$DEPLOY_OPERATOR ALL=(root) NOPASSWD: /usr/local/sbin/ksp-control-panel-apply-deploy /tmp/ksp-control-panel.tar.gz
EOF
visudo -cf /etc/sudoers.d/ksp-control-panel-deploy
chmod 0440 /etc/sudoers.d/ksp-control-panel-deploy

systemctl daemon-reload
systemctl enable ksp-backend >/dev/null
nginx -t
systemctl reload nginx || systemctl restart nginx
