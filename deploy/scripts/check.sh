#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "== docker compose ps =="
docker compose ps

echo
echo "== backend health =="
curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8001}/health"

echo
echo
echo "== recent logs =="
docker compose logs --tail=50 backend worker frontend
