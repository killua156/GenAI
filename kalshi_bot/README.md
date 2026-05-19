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
├── requirements.txt
├── .env.example
├── tests/             # pytest unit tests
├── reports/           # generated reports (gitignored)
└── state/             # prior prices (gitignored)
```

## Limitations

- First run with `--mode movers` has no prior state; falls back to in-market `previous_yes_ask` (prior tick, not yesterday). Subsequent runs use proper diffs.
- Pricing constants in `costs.py` are accurate as of build time. Update if Anthropic changes rates.
- The state file is capped at 500 most-recent tickers to prevent unbounded growth.
- Top-by-volume markets tend to be the most efficient; `movers` and `illiquid` modes exist precisely to look where edge is likelier.
- No authentication, no order placement, no backtest, no calibration tracking — out of scope by design.
