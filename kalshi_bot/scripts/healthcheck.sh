#!/usr/bin/env bash
# One-glance status check for the kalshi_bot cron setup.
#
# Exits 0 if healthy, 1 if any problem detected. Safe to run anytime —
# read-only, no API calls, no cost.
#
# Suggested use:
#   ./scripts/healthcheck.sh                   # when you want to check in
#   ./scripts/healthcheck.sh || echo "CHECK"   # one-liner alerting (via mail/push/etc.)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

problems=0
pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; problems=$((problems + 1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }

echo "kalshi_bot health check — $(date -u '+%Y-%m-%d %H:%M:%S')Z"
echo

echo "Config"
if [ -f .env ] && grep -q '^ANTHROPIC_API_KEY=' .env; then
  key_prefix=$(grep '^ANTHROPIC_API_KEY=' .env | head -1 | cut -d= -f2 | cut -c1-10)
  pass ".env has ANTHROPIC_API_KEY (${key_prefix}…)"
else
  fail ".env missing or has no ANTHROPIC_API_KEY"
fi

if command -v python3 >/dev/null 2>&1 || [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  pass "python interpreter available"
else
  fail "no python3 or .venv found"
fi

echo
echo "Cron"
if crontab -l 2>/dev/null | grep -q "run_daily.sh"; then
  pass "run_daily.sh scheduled in crontab"
else
  fail "run_daily.sh NOT scheduled (crontab -l doesn't mention it)"
fi
if crontab -l 2>/dev/null | grep -q "run_resolve.sh"; then
  pass "run_resolve.sh scheduled in crontab"
else
  warn "run_resolve.sh not scheduled (optional, but recommended for weekly eval)"
fi

echo
echo "Runs"
latest_log=$(ls -t logs/bot-*.log 2>/dev/null | head -1 || true)
if [ -z "$latest_log" ]; then
  fail "no bot runs logged yet — expected logs/bot-YYYY-MM-DD.log"
else
  # Portable mtime: GNU stat (-c) vs BSD/macOS stat (-f)
  mtime=$(stat -c %Y "$latest_log" 2>/dev/null || stat -f %m "$latest_log" 2>/dev/null || echo 0)
  age_hours=$(( ($(date +%s) - mtime) / 3600 ))
  if [ "$age_hours" -lt 36 ]; then
    pass "last run was ${age_hours}h ago ($(basename "$latest_log"))"
  else
    fail "last run was ${age_hours}h ago — expected <36h. Did cron fire?"
  fi
  if grep -qE "ANALYSIS FAILED|REFUSING|Traceback|ERROR:" "$latest_log"; then
    fail "errors found in $(basename "$latest_log") — grep ERROR/Traceback"
  else
    pass "latest log is clean (no errors)"
  fi
fi

report_count=$(find reports -maxdepth 1 -name '*.json' ! -name 'EVAL.json' 2>/dev/null | wc -l | tr -d ' ')
pass "$report_count report file(s) in reports/"

partial_count=$(find reports/.partial -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
if [ "$partial_count" -gt 0 ]; then
  warn "$partial_count partial file(s) in reports/.partial/ — a run may have crashed; try --resume"
fi

echo
echo "Eval"
if [ -f reports/EVAL.md ]; then
  eval_mtime=$(stat -c %Y reports/EVAL.md 2>/dev/null || stat -f %m reports/EVAL.md 2>/dev/null || echo 0)
  eval_age_hours=$(( ($(date +%s) - eval_mtime) / 3600 ))
  pass "reports/EVAL.md exists (${eval_age_hours}h old)"
else
  warn "reports/EVAL.md doesn't exist yet — run ./scripts/run_resolve.sh"
fi

echo
if [ "$problems" -gt 0 ]; then
  printf "\033[31m%d problem(s) detected.\033[0m\n" "$problems"
  exit 1
fi
printf "\033[32mAll checks passed.\033[0m\n"
exit 0
