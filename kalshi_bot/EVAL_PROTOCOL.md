# Kalshi Bot — Paper Trading Evaluation Protocol v1

**Pre-registered before Day 1 of testing. Do not amend during the test — committing to the rules upfront is what makes this an evaluation and not a vibe check.**

## Purpose

Measure whether the bot's recommendations are predictive enough to risk real money. Treat this as a disciplined pre-flight check, not a final answer — 1 week is too short for statistical confidence.

## Test window

- **Pick-generation period:** Day 1 through Day 7 (one bot run per day).
- **Resolution window:** Day 1 through Day 14, giving picks up to a week to settle.
- **Final evaluation:** Day 14 or later, once `resolve.py` reports a stable number of resolved BUYs.

## Bot configuration — frozen for the test

Do not change these between runs. Changing config mid-test invalidates the measurement.

| Flag | Value |
|---|---|
| `--model` | `claude-sonnet-4-6` |
| `--top` | `10` |
| `--mode` | `volume` (baseline — try `movers`/`illiquid` in a follow-up week) |
| `--max-days-to-close` | `10` (so picks resolve inside the window) |
| `--max-cost` | `2.0` |
| `--max-searches` | `5` |

Prompts, selection logic, and the scoring tool schema are also frozen. No prompt tweaks mid-week.

## What gets logged

Every run writes a `reports/{run_id}.json` with, per market:

- Ticker, title, event, category
- YES bid/ask and NO bid/ask at recommendation time
- `recommendation` (BUY_YES | BUY_NO | PASS)
- `confidence` (LOW | MEDIUM | HIGH)
- `edge_pp`, `my_estimate_pct`, `market_implied_pct`
- `reasoning` + `key_sources`
- Claude's `_usage` (for actual cost accounting)

**These JSON files are the authoritative trade log. No manual edits.**

## Paper-trade simulation rules

- **Position size:** 1 contract per BUY pick. Flat sizing — no Kelly, no scaling.
- **Entry price:** YES ask (for BUY_YES) or NO ask (for BUY_NO) at pick time — the number already in the JSON. Simulates immediately crossing the spread.
- **Hold to resolution:** no mid-market exits. P&L is realized when Kalshi settles.
- **PASS:** zero P&L (no position taken). Still contributes to the Brier score — the probability estimate is a prediction either way.
- **No slippage, no fees** in the paper book. Kalshi's fees are small for personal volume and would just add noise at this stage.

## Metrics `resolve.py` reports

Primary — BUY picks only:
- **Hit rate** = wins / resolved BUYs, where win = pnl_cents > 0
- **Total paper P&L** (cents)
- **Mean P&L per BUY** (cents)

Secondary — all resolved picks (incl. PASS):
- **Brier score** = mean of (my_estimate_pct / 100 − actual)². Baseline 0.25 = "always say 50%". Lower is better.

Buckets:
- Hit rate and P&L split by confidence (LOW / MEDIUM / HIGH). HIGH should outperform LOW; if not, the model's confidence is uncalibrated.

## Pre-committed decision rules

Evaluate once **at least 10 BUYs have resolved**. If fewer than 10 by Day 14, extend the resolution window — don't move the goalposts.

| Outcome | Decision |
|---|---|
| Mean P&L per BUY > **+5¢** AND Brier < **0.22** AND HIGH-confidence hit rate > 60% | Promising. Run a second paper week with `--mode movers`, then decide. |
| Mean P&L per BUY between **−5¢ and +5¢** | Inconclusive sample. Run another paper week before any decision. |
| Mean P&L per BUY < **−5¢** OR Brier > **0.26** | Net-negative or worse than a coin flip. Refine prompts, re-paper-trade. **Do NOT go live.** |

**Even in the "promising" case: no real money off a single 1-week sample.** The pre-committed next step is additional paper weeks, not real trades.

## Known limitations of this eval

- 1 week ≈ 10–20 BUYs — statistical noise can swamp real signal.
- `--max-days-to-close 10` biases toward near-resolution markets, which may behave differently from longer-horizon markets.
- No category/market-type stratification — a week that only picked NFL games tells you about NFL, not Kalshi broadly. Spot-check that the picks cover ≥3 categories.
- Entry prices are snapshotted at pick time; real execution would get a slightly different fill as the orderbook moves.
- Hold-to-resolution assumes no panic exits. In real trading, you'll be tempted. Account for that mentally.

## Out of scope — do not measure here

- Live execution slippage, fills, Kalshi fees
- Position sizing / Kelly / portfolio risk
- Correlation across picks (two markets on the same event aren't independent)
- Max drawdown or risk-of-ruin

These matter when you go live. Not before.

## Running the test

```bash
# Daily, Days 1-7 (manual or via cron):
cd kalshi_bot
python bot.py \
  --mode volume \
  --top 10 \
  --model claude-sonnet-4-6 \
  --max-days-to-close 10 \
  --max-cost 2.0 \
  --no-prompt

# Day 7 onward (and again on Day 14):
python resolve.py
cat reports/EVAL.md
```

`reports/EVAL.md` + `reports/EVAL.json` carry the authoritative numbers. Compare against the decision rules above.
