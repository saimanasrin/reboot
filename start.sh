#!/usr/bin/env bash
# Q-Chain AI - one-command local setup + run (macOS / Linux). Use --dev for hot reload, --reseed to rebuild data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
if [[ "${*}" == *--reseed* || ! -f qchain.db ]]; then .venv/bin/python -m app.seed; fi
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
if [[ "${*}" == *--dev* ]]; then
  (cd "$ROOT/backend" && .venv/bin/python -m uvicorn app.main:app --reload --port 8000) &
  npm run dev
else
  npm run build
  cd "$ROOT/backend" && echo "Open http://127.0.0.1:8000" && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
fi
