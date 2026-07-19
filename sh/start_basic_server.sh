#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "Starting basic_server.py on ${HOST}:${PORT}"
exec uv run uvicorn basic_server:app --host "${HOST}" --port "${PORT}"
