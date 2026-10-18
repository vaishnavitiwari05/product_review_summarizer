#!/usr/bin/env bash
# Live end-to-end check: starts the real backend (temp SQLite DB, offline NLP backends, mock LLM),
# runs the frontend's live tests against it over real HTTP, then stops the backend.
#   usage: scripts/e2e.sh            (from the project root)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${E2E_PORT:-8765}"
PY="${PYTHON:-python3}"
DB="$(mktemp -d)/e2e.db"

cd "$ROOT/backend"
DATABASE_URL="sqlite:///$DB" SENTIMENT_BACKEND=vader EMBEDDING_BACKEND=tfidf USE_MOCK_LLM=true \
MAX_UPLOAD_MB=1 CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173" \
  "$PY" -m uvicorn app.main:app --port "$PORT" --log-level warning &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { echo "Backend did not start"; exit 1; }
echo "Backend up on :$PORT"

cd "$ROOT/frontend"
E2E_API_URL="http://127.0.0.1:$PORT" npm run test:e2e
