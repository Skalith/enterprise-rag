#!/usr/bin/env bash
# Start backend (uvicorn --reload), Celery worker and frontend (next dev)
# in one tmux session so all three logs stream side by side.
#
# Usage:  scripts/dev.sh          # start (or re-attach)
#         scripts/dev.sh stop     # kill the session
#
# Infrastructure (postgres, redis, qdrant, minio) is expected to already be
# running in Docker:  docker compose up -d postgres redis qdrant minio
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="enterprise-rag"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

if [[ "${1:-}" == "stop" ]]; then
  tmux kill-session -t "$SESSION" 2>/dev/null && echo "Stopped '$SESSION'." || echo "No '$SESSION' session running."
  exit 0
fi

if ! command -v tmux >/dev/null; then
  echo "tmux is required. Install it, or run the three processes in separate terminals." >&2
  exit 1
fi

if [[ ! -x "$BACKEND/venv/bin/uvicorn" ]]; then
  echo "Backend venv missing: $BACKEND/venv/bin/uvicorn" >&2
  exit 1
fi

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "Frontend deps missing. Run: (cd frontend && npm install)" >&2
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists — attaching."
  exec tmux attach -t "$SESSION"
fi

tmux new-session -d -s "$SESSION" -c "$BACKEND" -n dev
tmux send-keys -t "$SESSION:dev" \
  "./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 2357" C-m

tmux split-window -v -t "$SESSION:dev" -c "$BACKEND"
tmux send-keys -t "$SESSION:dev.1" \
  "./venv/bin/celery -A app.workers.celery_app worker -l info" C-m

tmux split-window -v -t "$SESSION:dev" -c "$FRONTEND"
tmux send-keys -t "$SESSION:dev.2" \
  "npm run dev" C-m

tmux select-layout -t "$SESSION:dev" tiled
tmux select-pane -t "$SESSION:dev.0"
exec tmux attach -t "$SESSION"
