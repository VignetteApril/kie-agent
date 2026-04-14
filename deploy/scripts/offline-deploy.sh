#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ARCHIVE_NAME="${1:-kie-agent-images.tar}"

if [[ ! -f ".env" ]]; then
  echo "[ERROR] .env not found. Copy .env.example to .env and update the values first."
  exit 1
fi

if [[ ! -f "$ARCHIVE_NAME" ]]; then
  echo "[ERROR] Archive not found: $ARCHIVE_NAME"
  exit 1
fi

mkdir -p backend/data/uploads backend/data/outputs backend/data/logs

echo "[INFO] Loading Docker images from $ARCHIVE_NAME ..."
docker load -i "$ARCHIVE_NAME"

echo "[INFO] Starting containers without rebuilding..."
docker compose up -d

echo "[INFO] Current container status:"
docker compose ps

echo "[INFO] Backend health check:"
sleep 3
curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8001}/health" || {
  echo
  echo "[WARN] Health check failed. Inspect logs with:"
  echo "       docker compose logs --tail=200 backend worker frontend"
  exit 1
}

echo

echo "[OK] Offline deployment completed."
