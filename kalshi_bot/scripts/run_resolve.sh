#!/usr/bin/env bash
# Resolver wrapper for cron. Walks reports/*.json, queries Kalshi for each
# ticker's resolution, writes reports/EVAL.md + EVAL.json. Public endpoints
# only — no ANTHROPIC_API_KEY needed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PY="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PY="$(command -v python)"
else
  echo "ERROR: no Python interpreter found" >&2
  exit 127
fi

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/resolve-$(date -u +%Y-%m-%d).log"

{
  echo "=== $(date -u '+%Y-%m-%d %H:%M:%S')Z — starting resolver ==="
  "$PY" "$PROJECT_DIR/resolve.py"
  echo "=== $(date -u '+%Y-%m-%d %H:%M:%S')Z — finished ==="
} >>"$LOG_FILE" 2>&1

find "$LOG_DIR" -name "resolve-*.log" -type f -mtime +30 -delete 2>/dev/null || true
