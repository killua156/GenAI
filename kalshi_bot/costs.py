"""Model pricing and cost estimation for the bot.

Rates are USD per million tokens (or per search). Update if Anthropic changes them.
"""
from __future__ import annotations

from typing import Mapping

PRICING: Mapping[str, Mapping[str, float]] = {
    "claude-sonnet-4-6": {
        "in": 3.0, "in_cache_read": 0.30, "in_cache_write": 3.75,
        "out": 15.0, "search": 0.01,
    },
    "claude-opus-4-7": {
        "in": 15.0, "in_cache_read": 1.50, "in_cache_write": 18.75,
        "out": 75.0, "search": 0.01,
    },
    "claude-haiku-4-5-20251001": {
        "in": 0.80, "in_cache_read": 0.08, "in_cache_write": 1.00,
        "out": 4.0, "search": 0.01,
    },
}

AVG_INPUT_TOKENS_PER_MARKET = 4000
AVG_OUTPUT_TOKENS_PER_MARKET = 500


def _model_pricing(model: str) -> Mapping[str, float]:
    return PRICING.get(model, PRICING["claude-sonnet-4-6"])


def estimate(n_markets: int, model: str, max_searches: int) -> float:
    """Conservative upfront estimate (assumes no cache hits, all searches used)."""
    p = _model_pricing(model)
    per_market = (
        AVG_INPUT_TOKENS_PER_MARKET * p["in"] / 1_000_000
        + AVG_OUTPUT_TOKENS_PER_MARKET * p["out"] / 1_000_000
        + max_searches * p["search"]
    )
    return round(per_market * n_markets, 4)


def from_usage(usage: dict, model: str) -> float:
    """Compute actual cost from a single Anthropic message usage dict."""
    if not usage:
        return 0.0
    p = _model_pricing(model)
    in_tokens = int(usage.get("input_tokens", 0) or 0)
    out_tokens = int(usage.get("output_tokens", 0) or 0)
    cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
    server_tool_use = usage.get("server_tool_use") or {}
    searches = int(server_tool_use.get("web_search_requests", 0) or 0)
    cost = (
        in_tokens * p["in"] / 1_000_000
        + cache_read * p["in_cache_read"] / 1_000_000
        + cache_write * p["in_cache_write"] / 1_000_000
        + out_tokens * p["out"] / 1_000_000
        + searches * p["search"]
    )
    return round(cost, 4)
