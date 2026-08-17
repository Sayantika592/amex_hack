#!/usr/bin/env bash
# One-command demo: initialise DB, validate taxonomy, generate + validate data,
# seed demo cases (incl. Rahul), run the Rahul pipeline, start backend + frontend.
set -euo pipefail
cd "$(dirname "$0")/.."

COUNT="${COUNT:-1000}"
SEED="${SEED:-42}"

if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example"; fi
set -a; source .env; set +a

echo "== 1/7 Initialising database + taxonomy =="
python -m backend.db.init

echo "== 2/7 Validating taxonomy (tech-doc vs Excel) =="
python -m validation.validate_taxonomy

echo "== 3/7 Generating ${COUNT} synthetic disputes (seed ${SEED}) + demo cases =="
python -m data.generate --count "${COUNT}" --seed "${SEED}"

echo "== 4/7 Validating generated dataset =="
python -m data.validate

echo "== 5/7 Running the Rahul case end-to-end =="
python -m evaluation.run_rahul

echo "== 6/7 Starting backend on :${API_PORT:-8000} =="
uvicorn backend.api.app:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" &
BACKEND_PID=$!
trap 'kill ${BACKEND_PID} 2>/dev/null || true' EXIT

echo "== 7/7 Starting frontend on :5173 =="
cd frontend
[ -d node_modules ] || npm install --no-audit --no-fund
echo
echo ">>> Open http://localhost:5173  (backend API: http://localhost:${API_PORT:-8000}/api/health)"
echo ">>> Demo cases: http://localhost:5173/demo"
npm run dev -- --host
