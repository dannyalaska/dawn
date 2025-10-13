#!/bin/bash
# === DAWN Startup Script ===
# Starts Redis + Postgres + FastAPI API + Streamlit frontend

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

API_PID=""
OLLAMA_PID=""

if [[ -f ".env" ]]; then
  echo "📦 Loading environment from .env"
  tmp_env="$(mktemp)"
  python3 - <<'PY' >"$tmp_env"
import shlex
from pathlib import Path

def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if "#" in value:
            hash_idx = value.find("#")
            if hash_idx == 0 or value[hash_idx - 1].isspace():
                value = value[:hash_idx].rstrip()
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key] = value
    return data

env_path = Path(".env")
for k, v in parse_env(env_path).items():
    print(f'{k}={shlex.quote(v)}')
PY
  set -a
  source "$tmp_env"
  set +a
  rm -f "$tmp_env"
fi

echo "🚀 Starting DAWN environment (LLM_PROVIDER=${LLM_PROVIDER:-stub})..."

if command -v brew >/dev/null 2>&1; then
  start_service() {
    local svc="$1"
    if brew list --versions "$svc" >/dev/null 2>&1; then
      if brew services start "$svc" >/dev/null 2>&1; then
        echo "✅ Brew service '${svc}' running."
        return 0
      else
        echo "⚠️  Failed to start brew service '${svc}'."
        return 1
      fi
    fi
    return 1
  }

  start_service redis || echo "⚠️  Redis formula not installed; start Redis manually."

  postgres_started=false
  for candidate in postgresql postgresql@16 postgresql@15 postgresql@14; do
    if start_service "$candidate"; then
      postgres_started=true
      break
    fi
  done
  if [[ "${postgres_started}" != "true" ]]; then
    echo "⚠️  No Homebrew PostgreSQL service found; ensure your database is running."
  fi
else
  echo "⚠️  Homebrew not found; make sure Redis and Postgres are running."
fi

if [[ "${LLM_PROVIDER:-stub}" == "ollama" ]]; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "⚠️  Ollama CLI not found. Install from https://ollama.ai/download to use local models."
  else
    export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3}"
    if ! curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      echo "🦙 Starting Ollama server..."
      ollama serve >"${TMPDIR:-/tmp}/dawn_ollama.log" 2>&1 &
      OLLAMA_PID=$!
      for _ in {1..20}; do
        if curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
          echo "✅ Ollama API is up."
          break
        fi
        if ! ps -p "${OLLAMA_PID}" >/dev/null 2>&1; then
          echo "⚠️  Ollama server exited unexpectedly; check ${TMPDIR:-/tmp}/dawn_ollama.log."
          OLLAMA_PID=""
          break
        fi
        sleep 0.5
      done
    else
      echo "🦙 Ollama server already running."
    fi

    echo "📦 Ensuring Ollama model '${OLLAMA_MODEL}' is available..."
    if ! ollama show "${OLLAMA_MODEL}" >/dev/null 2>&1; then
      if ollama pull "${OLLAMA_MODEL}"; then
        echo "✅ Pulled Ollama model '${OLLAMA_MODEL}'."
      else
        echo "⚠️  Failed to pull Ollama model '${OLLAMA_MODEL}'. DAWN will continue but responses may fail."
      fi
    fi
  fi
fi

poetry env use python3.11
source "$(poetry env info --path)/bin/activate"

if [[ "${LLM_PROVIDER:-}" == "openai" && -n "${OPENAI_BASE_URL:-}" ]]; then
  echo "🔍 Checking LM Studio / OpenAI endpoint at ${OPENAI_BASE_URL}"
  if ! curl -fsS --max-time 2 "${OPENAI_BASE_URL%/}/models" >/dev/null; then
    echo "⚠️  Could not reach ${OPENAI_BASE_URL}; continuing anyway."
  fi
fi

echo "🗄️  Running database migrations..."
poetry run alembic upgrade head

cleanup() {
  if [[ -n "${API_PID}" ]] && ps -p "${API_PID}" >/dev/null 2>&1; then
    kill "${API_PID}" || true
  fi
  if [[ -n "${OLLAMA_PID}" ]] && ps -p "${OLLAMA_PID}" >/dev/null 2>&1; then
    kill "${OLLAMA_PID}" || true
  fi
}

trap cleanup EXIT

poetry run uvicorn app.api.server:app --port 8000 --reload &
API_PID=$!

for _ in {1..20}; do
  if curl -s http://127.0.0.1:8000/health >/dev/null; then
    echo "✅ API is up"
    break
  fi
  sleep 0.5
done

poetry run streamlit run app/streamlit_app/main.py --server.port 8501
