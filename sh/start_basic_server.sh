#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is required for deployment. Refusing to use the local development default." >&2
  exit 1
fi

export REQUIRE_DATABASE_URL="${REQUIRE_DATABASE_URL:-1}"
export REQUIRE_SAFE_DATABASE_URL="${REQUIRE_SAFE_DATABASE_URL:-1}"

echo "Starting basic_server.py on ${HOST}:${PORT}"
exec uv run uvicorn basic_server:app --host "${HOST}" --port "${PORT}"
