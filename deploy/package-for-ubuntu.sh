#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/deploy/dist"
ARCHIVE="$OUT_DIR/ksp-control-panel.tar.gz"

mkdir -p "$OUT_DIR"
rm -f "$ARCHIVE"

tar \
  --exclude='./deploy/dist' \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/dist' \
  --exclude='./backend/.runtime' \
  --exclude='./backend/__pycache__' \
  --exclude='./backend/maneuvers/__pycache__' \
  --exclude='./.python-deps' \
  --exclude='./.pip-cache' \
  --exclude='./.git' \
  -czf "$ARCHIVE" \
  -C "$ROOT_DIR" \
  .

echo "$ARCHIVE"
