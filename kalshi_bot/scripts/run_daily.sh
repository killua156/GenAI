#!/usr/bin/env bash
# Daily bot wrapper for cron. Resolves paths explicitly because cron doesn't
# inherit your shell PATH or working directory.
#
# Config is frozen to the EVAL_PROTOCOL.md defaults — do not edit mid-week.

set -euo pipefail

# Project root = parent of this script's directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Ensure a sane PATH for cron.
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Prefer the project's venv; fall back to system python3/python.
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

# Per-day log file so grep/tail is sane.
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/bot-$(date -u +%Y-%m-%d).log"

{
  echo "=== $(date -u '+%Y-%m-%d %H:%M:%S')Z — starting daily run ==="
  echo "cwd: $PROJECT_DIR"
  echo "python: $PY ($("$PY" --version 2>&1))"

  "$PY" "$PROJECT_DIR/bot.py" \
    --mode volume \
    --top 10 \
    --max-days-to-close 10 \
    --max-cost 2.0 \
    --max-searches 5 \
    --no-prompt

  echo "=== $(date -u '+%Y-%m-%d %H:%M:%S')Z — finished ==="
} >>"$LOG_FILE" 2>&1

# Rotate logs: keep last 30 days.
find "$LOG_DIR" -name "bot-*.log" -type f -mtime +30 -delete 2>/dev/null || true
