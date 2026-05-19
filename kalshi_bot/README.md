# Kalshi Bot

A daily bot that scans Kalshi prediction markets, researches each one with Claude + web search, and writes a markdown report of suggested trades. Read-only — it does not place orders.

> Educational/research output. Not financial advice.

## How it works

1. Hits Kalshi's public REST API for currently-open markets and picks the highest-volume ones.
2. For each market, asks Claude (with the `web_search` tool) to research the underlying event, estimate a probability, compare it to the market's implied probability, and produce a `BUY YES` / `BUY NO` / `PASS` recommendation with confidence and reasoning.
3. Aggregates everything into `reports/YYYY-MM-DD.md`, with actionable picks at the top.

## Setup

```bash
cd kalshi_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and put your ANTHROPIC_API_KEY in it
```

You also need to enable the web search tool in the Claude Console (Settings → Privacy).

## Run

```bash
# Default: analyze top 10 highest-volume open markets
python bot.py

# Inspect what would be analyzed without spending tokens
python bot.py --dry-run

# More markets, larger search budget per market
python bot.py --top 20 --max-searches 8

# Restrict to one event (e.g. all sub-markets of a specific event)
python bot.py --event KXNFLGAME-25NOV09SFLAR

# Use Opus 4.7 for deeper analysis (slower, more expensive)
python bot.py --model claude-opus-4-7
```

The report lands in `reports/YYYY-MM-DD.md`. Re-running on the same day overwrites it.

## Layout

```
kalshi_bot/
├── bot.py             # CLI entry point
├── kalshi_client.py   # Public Kalshi REST client
├── analyzer.py        # Claude + web_search analyzer
├── report.py          # Markdown report writer
├── requirements.txt
├── .env.example
└── reports/           # Generated reports (gitignored)
```

## Tuning

- `--min-volume`: skip thinly-traded markets. Default 1000 contracts/24h.
- `--top`: how many markets to analyze. Each one costs ~one Claude call + a few web searches (~$0.05-$0.20 depending on model).
- `--model`: `claude-sonnet-4-6` (default, fast/cheap) or `claude-opus-4-7` (slower, more thorough).
- `KALSHI_API_BASE` env var: override the API base if Kalshi changes it.

## Schedule it

To run it every morning, add a cron entry:

```cron
30 7 * * * cd /path/to/kalshi_bot && /path/to/.venv/bin/python bot.py --top 15 >> cron.log 2>&1
```

## Extending

Obvious next steps if you want more:

- Authenticated mode for orderbook depth, position tracking, or actually placing orders (Kalshi requires API key + RSA signed requests).
- Persist analyses to a SQLite DB and track recommendation P&L over time.
- Hybrid mode: run a cheap statistical screen first (e.g. order-book imbalance, price drift) to shortlist markets before paying for LLM analysis.
- Slack/email/webhook delivery of the report.
