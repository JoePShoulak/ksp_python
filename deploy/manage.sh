#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

REMOTE="${KSP_REMOTE:-hp4}"
ARCHIVE_LOCAL="$ROOT_DIR/deploy/dist/ksp-control-panel.tar.gz"
ARCHIVE_REMOTE="${KSP_ARCHIVE:-/tmp/ksp-control-panel.tar.gz}"
BOOTSTRAP_DIR="${KSP_BOOTSTRAP_DIR:-~/ksp-control-panel-deploy}"
APPLY="/usr/local/sbin/ksp-control-panel-apply-deploy"
SERVICE="${KSP_SERVICE:-ksp-backend}"

usage() {
  cat <<EOF
Usage: bash deploy/manage.sh <command>

Commands:
  deploy      Package, copy, and apply the deploy archive
  bootstrap   First-time deploy path that runs bootstrap from the archive
  up          Start the app service and reload Nginx
  down        Stop the app service
  restart     Restart the app service and reload Nginx
  package     Build the deploy archive only
  send        Build and copy the deploy archive only
EOF
}

package_app() {
  (cd "$ROOT_DIR" && bash deploy/package-for-ubuntu.sh)
}

send_app() {
  package_app
  scp "$ARCHIVE_LOCAL" "$REMOTE:$ARCHIVE_REMOTE"
}

deploy_app() {
  send_app
  ssh "$REMOTE" "sudo -n $APPLY $ARCHIVE_REMOTE"
}

bootstrap_app() {
  send_app
  ssh -t "$REMOTE" "rm -rf $BOOTSTRAP_DIR && mkdir -p $BOOTSTRAP_DIR && tar -xzf $ARCHIVE_REMOTE -C $BOOTSTRAP_DIR && cd $BOOTSTRAP_DIR && sudo bash deploy/ubuntu/bootstrap.sh && bash deploy/apply-deploy.sh $ARCHIVE_REMOTE"
}

up_app() {
  ssh "$REMOTE" "sudo -n systemctl start $SERVICE && sudo -n nginx -t && sudo -n systemctl reload nginx"
}

down_app() {
  ssh "$REMOTE" "sudo -n systemctl stop $SERVICE"
}

restart_app() {
  ssh "$REMOTE" "sudo -n systemctl restart $SERVICE && sudo -n nginx -t && sudo -n systemctl reload nginx"
}

case "${1:-}" in
  deploy)
    deploy_app
    ;;
  bootstrap)
    bootstrap_app
    ;;
  up)
    up_app
    ;;
  down)
    down_app
    ;;
  restart)
    restart_app
    ;;
  package)
    package_app
    ;;
  send)
    send_app
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $1" >&2
    usage >&2
    exit 64
    ;;
esac
