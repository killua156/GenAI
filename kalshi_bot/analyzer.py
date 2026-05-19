"""Claude-based analyzer with web_search; emits a structured recommendation via tool_use."""
from __future__ import annotations

import logging
from typing import Optional

from anthropic import Anthropic, APIError

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

SUBMIT_TOOL = {
    "name": "submit_recommendation",
    "description": "Submit your final analysis of the Kalshi market. Call this exactly once at the end of your turn.",
    "input_schema": {
        "type": "object",
        "properties": {
            "my_estimate_pct": {
                "type": "number", "minimum": 0, "maximum": 100,
                "description": "Your estimated probability the market resolves YES, 0-100.",
            },
            "market_implied_pct": {
                "type": "number", "minimum": 0, "maximum": 100,
                "description": "Current YES ask as a percentage (63¢ -> 63).",
            },
            "edge_pp": {
                "type": "number",
                "description": "my_estimate_pct minus market_implied_pct, signed percentage points.",
            },
            "recommendation": {
                "enum": ["BUY_YES", "BUY_NO", "PASS"],
                "description": "PASS unless edge is at least ~5pp with corroborating sources.",
            },
            "confidence": {"enum": ["LOW", "MEDIUM", "HIGH"]},
            "reasoning": {
                "type": "string", "maxLength": 800,
                "description": "2-4 sentences citing the key evidence behind the estimate.",
            },
            "key_sources": {
                "type": "array", "items": {"type": "string"}, "maxItems": 5,
                "description": "Up to 5 URLs that materially supported your view.",
            },
        },
        "required": [
            "my_estimate_pct", "market_implied_pct", "edge_pp",
            "recommendation", "confidence", "reasoning", "key_sources",
        ],
    },
}

SYSTEM_PROMPT = """You are an expert prediction-market analyst for Kalshi event contracts.

For each market:
1. Read the title, rules, and YES/NO prices. The YES ask in cents equals the market's implied YES probability in percent.
2. Use the web_search tool to research recent, authoritative sources for the underlying event. Prefer primary sources, official data, established news, and forecast aggregators. Be skeptical of speculation.
3. Form your own probability estimate for YES.
4. Compute edge_pp = your estimate − market implied.
5. Recommend BUY_YES, BUY_NO, or PASS. Require at least ~5pp of edge AND multiple corroborating sources before a non-PASS action. PASS when liquidity is thin, evidence is weak, or the event is too far out for confident assessment.
6. End your turn by calling submit_recommendation with all required fields. Do not call any tool after submit_recommendation. Never end without calling it.

Be calibrated. Most markets should resolve to PASS. Never invent facts; if search results are inadequate, submit PASS with LOW confidence and explain why in reasoning.
"""

STRICT_RETRY_SUFFIX = (
    "\n\nIMPORTANT: You must call the submit_recommendation tool exactly once before ending your turn. "
    "Do not respond with plain text. Submit the structured recommendation now."
)


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

    def analyze(self, market: dict, orderbook_summary: Optional[str] = None) -> dict:
        """Return a dict matching SUBMIT_TOOL.input_schema, plus '_usage'. Always returns a dict."""
        prompt = self._format_market(market, orderbook_summary)

        result = self._call_once(prompt)
        if result is not None:
            return result
        log.warning("analyzer: model did not call submit_recommendation; retrying with stricter prompt")

        result = self._call_once(prompt + STRICT_RETRY_SUFFIX)
        if result is not None:
            return result
        log.warning("analyzer: retry also missed submit_recommendation; returning PASS/LOW fallback")
        return self._fallback("Model failed to submit a structured recommendation after one retry.")

    def _call_once(self, user_text: str) -> Optional[dict]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": self.max_searches,
                    },
                    SUBMIT_TOOL,
                ],
                messages=[{"role": "user", "content": user_text}],
            )
        except APIError as e:
            log.warning("analyzer: Anthropic API error: %s", e)
            return None

        for block in response.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == "submit_recommendation"
            ):
                data = dict(block.input)
                data["_usage"] = _usage_dict(response.usage)
                return data
        return None

    @staticmethod
    def _fallback(reason: str) -> dict:
        return {
            "my_estimate_pct": 50,
            "market_implied_pct": 50,
            "edge_pp": 0,
            "recommendation": "PASS",
            "confidence": "LOW",
            "reasoning": reason,
            "key_sources": [],
            "_usage": {},
        }

    @staticmethod
    def _format_market(m: dict, ob_summary: Optional[str]) -> str:
        rules = (m.get("rules_primary") or "")[:800]
        v24 = m.get("volume_24h") or 0
        lines = [
            "Analyze this Kalshi market. End your turn by calling submit_recommendation.",
            "",
            f"**Title:** {m.get('title')}",
            f"**Subtitle:** {m.get('subtitle') or m.get('yes_sub_title') or ''}",
            f"**Ticker:** {m.get('ticker')}",
            f"**Event:** {m.get('event_ticker', '')}",
            f"**Category:** {m.get('category', '')}",
            f"**Close time (UTC):** {m.get('close_time')}",
            f"**YES bid / ask:** {m.get('yes_bid')}¢ / {m.get('yes_ask')}¢",
            f"**NO bid / ask:** {m.get('no_bid')}¢ / {m.get('no_ask')}¢",
            f"**Last trade:** {m.get('last_price')}¢",
            f"**Volume 24h:** {v24:,}",
            f"**Open interest:** {m.get('open_interest', 0)}",
            f"**Liquidity:** {m.get('liquidity', 0)}",
        ]
        if ob_summary:
            lines.append(f"**Order book:** {ob_summary}")
        lines += ["", f"**Rules:** {rules}"]
        return "\n".join(lines)


def _usage_dict(usage) -> dict:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        try:
            return usage.model_dump()
        except Exception:
            pass
    try:
        return dict(usage)
    except Exception:
        return {}
