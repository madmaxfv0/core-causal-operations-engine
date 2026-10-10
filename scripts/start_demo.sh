#!/usr/bin/env bash
# START CORE DEMO — one command: installs Python deps, initialises demo data (if needed), builds the UI (if node is present and dist is missing), starts the server.
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then $PY -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r backend/requirements.txt
if [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then (cd frontend && npm install --no-audit --no-fund && npm run build); else echo "frontend/dist missing and npm not found: install Node 18+ and run: cd frontend && npm install && npm run build"; exit 1; fi
fi
python scripts/init_demo.py
echo "CORE is starting on http://localhost:${PORT:-8000}"
exec uvicorn backend.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
