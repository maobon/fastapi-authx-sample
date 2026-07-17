#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

handle_error() {
  local exit_code=$?
  echo "ERROR: basic_server.py tests failed with exit code ${exit_code}." >&2
  echo "See pytest output above for the failed test and traceback." >&2
  exit "${exit_code}"
}

trap handle_error ERR

echo "Running basic_server.py tests..."
uv run pytest -x -q test/test_basic_server.py
echo "basic_server.py tests passed."
