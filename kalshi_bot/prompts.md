# Kalshi Trade Ideas — Claude Chat Prompts

Paste any of these into a fresh Claude.ai conversation (use Sonnet 4.6 for daily use, Opus 4.7 for deep dives). Make sure **web search is enabled** in your profile (Settings → Profile → Capabilities).

These are an alternative to running the bot — useful when you just want a few ideas and don't want to set up the Python script.

---

## 1. Daily sweep (5–7 markets across categories)

```
You are an expert prediction-market analyst. Use web search to find currently-open Kalshi prediction markets and recommend trades for me. Be calibrated and honest about uncertainty — most markets should resolve to PASS.

Process:

1. Search for currently-open Kalshi markets. Pick 5–7 across different categories (politics, sports, economics, weather, Fed/inflation, etc.) that meet ALL of:
   - meaningful 24h trading volume (skip thinly-traded markets)
   - resolves within ~30 days (skip multi-year bets)
   - has a recent news catalyst worth researching

2. For each market, search the web for:
   - Recent (last 7 days) authoritative news
   - Primary sources, official data, polling, expert consensus
   - Any base rates from similar past events

3. Compare your probability estimate to the market's implied probability. The YES ask in cents equals implied % (e.g. 63¢ = 63%).
   - BUY YES if your estimate is at least 5pp HIGHER than implied AND multiple sources agree
   - BUY NO if your estimate is at least 5pp LOWER AND multiple sources agree
   - Otherwise PASS

Output each market in exactly this format:

### {Market title}
- **Ticker:** `KX-...`
- **Kalshi link:** {URL}
- **YES ask:** XX¢ ({XX}% implied)
- **My estimate:** XX%
- **Edge:** {±X} pp
- **Recommendation:** BUY YES | BUY NO | PASS
- **Confidence:** LOW | MEDIUM | HIGH
- **Reasoning:** 2–4 sentences citing the key evidence.
- **Sources:**
  - {URL} — {what it told you}
  - {URL} — {what it told you}

At the end, give me a summary table sorted by confidence then |edge|:

| Ticker | Title | Rec | Conf | Edge |
|---|---|---|---|---|

Hard rules:
- Bias toward PASS. Real edge < 5pp = PASS. No fresh evidence = PASS.
- Don't fabricate URLs, prices, or numbers. Only cite sources you actually retrieved.
- Anything resolving more than 30 days out: max confidence is MEDIUM.
- The YES/NO prices you report might be slightly stale — note that and tell me to verify on kalshi.com before trading.
- This is research, not financial advice.
```

---

## 2. Single-market deep dive

Use this when you've found a market you want to think hard about. Paste the Kalshi URL or ticker where indicated.

```
You are an expert prediction-market analyst. I want a deep, steelmanned analysis of this Kalshi market:

{PASTE KALSHI URL OR TICKER HERE}

Use web search to:

1. Find the market on kalshi.com — current YES/NO prices, volume, resolution rules, close date.
2. Research the underlying event in depth (minimum: last 30 days of news, plus base rates from comparable past events). Use primary sources, official data, polling, expert forecasts.
3. Build the strongest possible case for YES. Then build the strongest possible case for NO. Steelman both, don't strawman either.
4. Form your own probability estimate independently of the market.
5. Compare to the market's implied probability. If your estimate differs by >5pp with corroborating evidence, recommend BUY YES or BUY NO. Otherwise PASS.

Bias toward PASS. Don't invent sources or numbers. If your research is inconclusive, say so and PASS with LOW confidence.

Format:

- **Market:** {title}
- **YES ask / NO ask:** XX¢ / XX¢ ({XX}% implied YES)
- **Resolves by:** {date}
- **My estimate:** XX%
- **Strongest YES case:** {paragraph citing evidence}
- **Strongest NO case:** {paragraph citing evidence}
- **What would change my mind:** {1–2 specific things to watch}
- **Recommendation:** BUY YES | BUY NO | PASS
- **Confidence:** LOW | MEDIUM | HIGH
- **Position-sizing note:** rough thought on whether this is a small/medium/big idea relative to bankroll
- **Sources:** numbered list of cited URLs with 1-line summaries

Verify the YES/NO prices on kalshi.com before I trade — they move.
```

---

## 3. Movers only (biggest 24-hour price changes)

```
You are an expert prediction-market analyst. Use web search to find Kalshi prediction markets whose YES price has moved at least 10 percentage points in the last 24–48 hours. Pick 5 of these movers and tell me whether each move is justified by news or is an overreaction.

For each market:

1. Identify the catalyst — what news, event, or release caused the move?
2. Assess whether the new price now reflects reality fully, undershoots it (more move to come), or overshoots it (mean reversion likely).
3. Recommend BUY YES, BUY NO, or PASS based on (2). Big moves often mean the market has already priced the news in — PASS unless you see a clear remaining edge.

Output each market in this format:

### {Market title}
- **Ticker:** `KX-...`
- **Move:** XX¢ → XX¢ ({±X} pp in {timeframe})
- **Catalyst:** {1-sentence summary of the news driver}
- **YES ask:** XX¢ ({XX}% implied now)
- **My estimate:** XX%
- **Edge remaining:** {±X} pp
- **Recommendation:** BUY YES | BUY NO | PASS
- **Confidence:** LOW | MEDIUM | HIGH
- **Reasoning:** 2–4 sentences on whether the move is right-sized.
- **Sources:** 2–3 URLs.

End with a summary table sorted by |edge remaining|:

| Ticker | Move | Rec | Conf | Edge left |
|---|---|---|---|---|

Bias toward PASS. Don't fabricate sources or numbers. Note that prices may be stale by the time I act.
```

---

## Tips for using these in Claude.ai

1. **Enable web search** (Settings → Profile → Capabilities → Web search). Without it, Claude is just guessing.
2. **Sonnet 4.6 for daily**, **Opus 4.7 for deep dives**. Opus is slower but catches more.
3. **Fresh chat each session.** Old context biases probability estimates.
4. **Click through every cited URL** before placing a trade. Hallucinated URLs do happen.
5. **Re-verify the YES/NO prices on kalshi.com.** Claude's web search may report stale numbers — prediction markets move fast.
6. **Track your picks.** Note Claude's recommendation + your action + the outcome in a spreadsheet. After 30–50 picks you'll know whether the calibration is actually working for your market mix.
7. **This is research, not financial advice.**
