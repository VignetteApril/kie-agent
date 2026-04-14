#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "[ERROR] .env not found. Copy .env.example to .env and update the values first."
  exit 1
fi

mkdir -p backend/data/uploads backend/data/outputs backend/data/logs

echo "[INFO] Building and starting KIE Agent containers..."
docker compose up -d --build

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
echo "[OK] Deployment completed."
