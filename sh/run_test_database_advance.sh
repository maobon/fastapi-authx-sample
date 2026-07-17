#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

handle_error() {
  local exit_code=$?
  echo "ERROR: database_advance.py tests failed with exit code ${exit_code}." >&2
  echo "See pytest output above for the failed test and traceback." >&2
  exit "${exit_code}"
}

trap handle_error ERR

echo "Running database_advance.py tests..."
uv run pytest -x -q test/test_database_advance.py
echo "database_advance.py tests passed."
