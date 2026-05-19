"""Claude-based analyzer that researches a Kalshi market via web search."""
from __future__ import annotations

from typing import Optional

from anthropic import Anthropic

SYSTEM_PROMPT = """You are an expert prediction market analyst specializing in Kalshi event contracts.

Your job: given a Kalshi market, produce a clear, evidence-backed trade recommendation.

Process for each market:
1. Read the market's title, rules, and current YES/NO prices. The YES ask in cents \
equals the market's implied probability of YES in percent (e.g. 63¢ = 63% implied).
2. Search the web for the most recent, authoritative news, polling, official sources, \
or data about the underlying event. Prefer primary sources (official sites, government \
data, established news, betting/forecast aggregators) over speculation.
3. Form your own probability estimate for YES based on the evidence.
4. Compute edge = (your estimate) − (market implied). Positive = YES is undervalued; \
negative = NO is undervalued (or YES is overvalued).
5. Decide: BUY YES, BUY NO, or PASS.
   - Require at least ~5 percentage points of edge AND multiple corroborating sources \
to recommend a non-PASS action.
   - PASS if liquidity is thin, evidence is weak/contradictory, or the close is far \
out and conditions can change a lot.
6. Assign confidence: LOW / MEDIUM / HIGH based on evidence quality and edge size.

Output EXACTLY this format (markdown), nothing before or after:

**My estimate:** <0-100>%
**Market implied:** <0-100>%
**Edge:** <signed pp, e.g. +8 or -3, or "none">
**Recommendation:** <BUY YES | BUY NO | PASS>
**Confidence:** <LOW | MEDIUM | HIGH>
**Reasoning:** <2-4 sentences citing the key evidence>
**Key sources:** <1-3 URLs separated by " | ">

Be honest about uncertainty. Most markets should be PASS. Never invent facts; if \
search results don't support a confident view, return PASS with LOW confidence.
"""

DEFAULT_MODEL = "claude-sonnet-4-6"


class Analyzer:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_searches: int = 5,
        max_tokens: int = 2048,
    ):
        self.client = Anthropic()
        self.model = model
        self.max_searches = max_searches
        self.max_tokens = max_tokens

    def analyze(self, market: dict, orderbook_summary: Optional[str] = None) -> str:
        prompt = self._format_market(market, orderbook_summary)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self.max_searches,
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(b.text for b in response.content if b.type == "text").strip()

    @staticmethod
    def _format_market(m: dict, ob_summary: Optional[str]) -> str:
        rules = (m.get("rules_primary") or "")[:800]
        lines = [
            "Analyze this Kalshi market and return a recommendation in the required format.",
            "",
            f"**Title:** {m.get('title')}",
            f"**Subtitle:** {m.get('subtitle', '') or m.get('yes_sub_title', '')}",
            f"**Ticker:** {m.get('ticker')}",
            f"**Event:** {m.get('event_ticker')}",
            f"**Category:** {m.get('category', '')}",
            f"**Close time (UTC):** {m.get('close_time')}",
            f"**YES bid / ask:** {m.get('yes_bid')}¢ / {m.get('yes_ask')}¢",
            f"**NO bid / ask:** {m.get('no_bid')}¢ / {m.get('no_ask')}¢",
            f"**Last trade:** {m.get('last_price')}¢",
            f"**Volume 24h:** {m.get('volume_24h'):,}" if m.get("volume_24h") is not None else "**Volume 24h:** ?",
            f"**Open interest:** {m.get('open_interest', '?')}",
            f"**Liquidity:** {m.get('liquidity', '?')}",
        ]
        if ob_summary:
            lines.append(f"**Order book:** {ob_summary}")
        lines += ["", f"**Rules:** {rules}"]
        return "\n".join(lines)


