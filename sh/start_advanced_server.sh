#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/advanced_server.log}"
PID_FILE="${PID_FILE:-${LOG_DIR}/advanced_server.pid}"

mkdir -p "${LOG_DIR}"

nohup uv run uvicorn advanced_server:app --host "${HOST}" --port "${PORT}" \
  >"${LOG_FILE}" 2>&1 </dev/null &
SERVER_PID=$!
echo "${SERVER_PID}" >"${PID_FILE}"

echo "Started advanced_server.py on ${HOST}:${PORT} (PID: ${SERVER_PID})"
echo "Log: ${LOG_FILE}"
