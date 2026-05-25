#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ksp-control-panel/app}"

install -m 0644 "$APP_DIR/deploy/ubuntu/ksp-backend.service" /etc/systemd/system/ksp-backend.service
install -m 0644 "$APP_DIR/deploy/ubuntu/ksp-control-panel.nginx" /etc/nginx/sites-available/ksp-control-panel
ln -sfn /etc/nginx/sites-available/ksp-control-panel /etc/nginx/sites-enabled/ksp-control-panel
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable ksp-backend >/dev/null
nginx -t
systemctl reload nginx || systemctl restart nginx
