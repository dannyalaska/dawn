#!/bin/bash
set -euo pipefail

echo "Running database migrations..."
poetry run alembic upgrade head

cleanup() {
  if [[ -n "${API_PID:-}" ]] && ps -p "${API_PID}" >/dev/null 2>&1; then
    kill "${API_PID}" || true
  fi
}

trap cleanup EXIT

echo "Starting FastAPI server..."
poetry run uvicorn app.api.server:app --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "Starting Streamlit..."
exec poetry run streamlit run app/streamlit_app/main.py --server.port 8501 --server.address 0.0.0.0 --browser.gatherUsageStats false
