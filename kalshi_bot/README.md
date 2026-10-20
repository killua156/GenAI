# Kalshi Bot

A daily bot that scans Kalshi prediction markets, researches each one with Claude + web search, and writes markdown + JSON reports of suggested trades. Read-only — it does not place orders.

> Educational/research output. Not financial advice. Verify before trading.

## How it works

1. Pulls open markets from Kalshi's public API and selects N via a configurable strategy:
   - **`volume`** (default): top by 24h volume
   - **`movers`**: biggest YES price change since the last run (uses local state)
   - **`illiquid`**: widest bid/ask spreads with a volume floor — where information edge tends to be highest
2. For each market, asks Claude (with the `web_search` tool) to research the event and submit a structured recommendation via tool_use (`BUY_YES` / `BUY_NO` / `PASS` with confidence, edge, reasoning, and sources).
3. Writes per-market results to a JSONL file as they complete, then aggregates into `reports/{run_id}.md` and `.json`.

Each run produces a fresh timestamped report — nothing is overwritten.

## Setup

```bash
cd kalshi_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env
```

Web search must be enabled in your Claude Console (Settings → Privacy).

## Run

```bash
# Default: top 10 by volume, $5 cost cap, interactive confirm
python bot.py

# Different selection strategies
python bot.py --mode movers
python bot.py --mode illiquid --top 5

# Inspect selection without spending tokens
python bot.py --dry-run
python bot.py --dry-run --mode illiquid

# Deeper analysis: more markets, more searches each
python bot.py --top 20 --max-searches 7 --max-cost 3.0

# Single event
python bot.py --event KXNFLGAME-25NOV09SFLAR

# Other models
python bot.py --model claude-opus-4-7          # pricier, more thorough
python bot.py --model claude-haiku-4-5-20251001 # cheaper, faster

# Cron-friendly (no interactive prompt)
python bot.py --no-prompt --max-cost 2.0

# Paper-trading mode: only pick markets that'll resolve inside your test window
python bot.py --max-days-to-close 10 --mode volume --no-prompt
```

## Paper-trading evaluation

Before risking real money, run the bot daily for a week and evaluate its picks against actual resolutions. See `EVAL_PROTOCOL.md` for the pre-registered rules (frozen config, decision thresholds, metrics).

```bash
# Day 1-7: generate picks (same config each day)
python bot.py --mode volume --top 10 --max-days-to-close 10 \
              --max-cost 2.0 --no-prompt

# Day 7+ (and again on Day 14): resolve picks and compute P&L + Brier score
python resolve.py
cat reports/EVAL.md
```

`resolve.py` walks every `reports/*.json`, hits Kalshi for each ticker's resolution, and produces:

- **Hit rate** (wins / resolved BUYs, 1 contract each)
- **Total and mean paper P&L** in cents
- **Brier score** across all probability estimates (incl. PASS). Lower is better; 0.25 is "always 50%".
- **Breakdown by confidence** so you can see whether HIGH actually outperforms LOW.

Output: `reports/EVAL.md` + `reports/EVAL.json`.

## Automate with cron

Two wrapper scripts in `scripts/` resolve paths and log properly so cron can call them directly:

- `scripts/run_daily.sh` — runs the bot with the frozen `EVAL_PROTOCOL.md` config
- `scripts/run_resolve.sh` — runs the resolver (no API key needed, public endpoints only)

Both write to `logs/{bot,resolve}-YYYY-MM-DD.log` (gitignored) and auto-prune logs older than 30 days. They prefer the project's `.venv/bin/python` and fall back to system `python3`.

### Install

```bash
cd /path/to/kalshi_bot

# 1. One-time setup: venv + deps + .env with your key
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && $EDITOR .env    # paste ANTHROPIC_API_KEY

# 2. Verify the wrapper works before scheduling
./scripts/run_daily.sh && tail logs/bot-*.log

# 3. Edit the crontab template, then install
sed -i "s|/ABSOLUTE/PATH/TO/kalshi_bot|$(pwd)|g" scripts/kalshi_bot.cron
crontab -l 2>/dev/null | cat - scripts/kalshi_bot.cron | crontab -
crontab -l    # confirm it's there
```

Default schedule:
- **Daily bot run at 07:30 local** — overnight news priced in, before the day starts.
- **Weekly resolver on Sundays at 20:00** — enough time for weekend sports/politics markets to settle.

Tweak the `30 7 * * *` and `0 20 * * 0` fields in `scripts/kalshi_bot.cron` before installing if you want a different schedule.

### Monitor

```bash
tail -f logs/bot-$(date -u +%Y-%m-%d).log       # today's run
ls -lt logs/                                     # recent runs
grep -l "ERROR\|Traceback" logs/*.log            # anything that went wrong
```

### Common gotchas

- **macOS:** cron needs Full Disk Access. System Settings → Privacy & Security → Full Disk Access → add `/usr/sbin/cron` and your terminal app. Alternative: use `launchd` with the equivalent schedule.
- **Timezone:** cron uses system local time. Verify with `date` on the machine running the job.
- **PATH:** the wrapper exports a sane PATH, but if your `python3` lives somewhere unusual, run `which python3` and either symlink into `/usr/local/bin` or edit the wrapper.
- **Failure alerting:** cron doesn't notify unless `MAILTO=` is set and the host has mail configured. Simplest alert for personal use: a weekly glance at `grep -c ERROR logs/*.log`.
- **First-run auth:** if the first scheduled run fails with "ANTHROPIC_API_KEY not set", your `.env` isn't being picked up. Confirm the file is in the project root and the script's `cd` landed in the right directory (check the log — it echoes `cwd:`).

### Disable

```bash
crontab -e    # delete the two kalshi_bot lines, save
# Or remove entirely: crontab -r (nuclear — removes ALL your cron entries)
```

## Outputs

```
reports/2026-05-19_073000.md     # human-readable, actionable picks first
reports/2026-05-19_073000.json   # machine-readable, includes raw usage data
state/last_prices.json           # tickers and prior YES asks, for movers mode
```

## Cost guardrails

Before any LLM call, the bot prints an estimate and refuses to proceed if it exceeds `--max-cost` (default $5). On TTY you also get a `Proceed? [y/N]` confirmation; `--no-prompt` skips it for cron.

After the run, the actual cost is summed from each `response.usage` and shown + persisted into the JSON.

Typical costs (10 markets, Sonnet 4.6, 5 searches each): roughly $0.70–$1.50. Opus 4.7: 4–5× that. Haiku: ~25% of Sonnet.

## Recovery after a crash

If the bot dies mid-run, the partial JSONL stays on disk:

```bash
ls reports/.partial/
python bot.py --resume reports/.partial/2026-05-19_073000.jsonl
# Regenerates .md + .json from completed markets, then deletes the partial.
```

## Cron

```cron
30 7 * * * cd /path/to/kalshi_bot && /path/to/.venv/bin/python bot.py --no-prompt --max-cost 1.50 --top 12 --mode volume >> cron.log 2>&1
```

## Tests

```bash
cd kalshi_bot
pytest tests/ -v
```

Mocked unit tests cover market cleaning, mode selection, tool-use extraction, retry/fallback paths, report rendering, cost math, and state persistence.

## Project layout

```
kalshi_bot/
├── bot.py             # CLI orchestrator
├── kalshi_client.py   # Public REST client; market cleaner; mode selectors
├── analyzer.py        # Claude + web_search; structured tool_use output
├── report.py          # Markdown + JSON writers; JSONL incremental persistence
├── costs.py           # Pricing table; estimate + from_usage
├── state.py           # last_prices.json read/write for movers diffing
├── resolve.py         # Paper-trade P&L + Brier evaluator
├── prompts.md         # Ready-to-paste Claude.ai chat prompts (manual alternative)
├── EVAL_PROTOCOL.md   # Pre-registered rules for the paper-trading week
├── scripts/           # Cron wrappers + crontab template
├── requirements.txt
├── .env.example
├── tests/             # pytest unit tests
├── reports/           # generated reports (gitignored)
├── logs/              # cron run logs (gitignored, auto-pruned at 30d)
└── state/             # prior prices (gitignored)
```

## Limitations

- First run with `--mode movers` has no prior state; falls back to in-market `previous_yes_ask` (prior tick, not yesterday). Subsequent runs use proper diffs.
- Pricing constants in `costs.py` are accurate as of build time. Update if Anthropic changes rates.
- The state file is capped at 500 most-recent tickers to prevent unbounded growth.
- Top-by-volume markets tend to be the most efficient; `movers` and `illiquid` modes exist precisely to look where edge is likelier.
- No authentication, no order placement, no backtest, no calibration tracking — out of scope by design.
