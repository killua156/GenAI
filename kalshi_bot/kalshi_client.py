"""Thin client for Kalshi's public REST endpoints."""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import requests

DEFAULT_BASE = "https://api.elections.kalshi.com/trade-api/v2"

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("ticker", "title", "yes_ask", "no_ask", "status")
INT_FIELDS = (
    "yes_bid", "yes_ask", "no_bid", "no_ask",
    "last_price", "previous_yes_ask", "previous_yes_bid", "previous_price",
    "volume", "volume_24h", "open_interest", "liquidity",
)


def _clean_market(m: dict) -> Optional[dict]:
    """Drop markets missing critical fields; coerce numeric fields to int."""
    for k in REQUIRED_FIELDS:
        v = m.get(k)
        if v is None or v == "":
            return None
    out = dict(m)
    for k in INT_FIELDS:
        try:
            out[k] = int(m.get(k) or 0)
        except (TypeError, ValueError):
            out[k] = 0
    return out


def close_within_days(market: dict, max_days: Optional[int]) -> bool:
    """True if `market` closes within max_days from now, or if max_days is None (no filter)."""
    if max_days is None:
        return True
    close_time = market.get("close_time")
    if not close_time:
        return False
    try:
        if close_time.endswith("Z"):
            close_time = close_time[:-1] + "+00:00"
        close_dt = datetime.fromisoformat(close_time)
    except (ValueError, AttributeError):
        return False
    if close_dt.tzinfo is None:
        close_dt = close_dt.replace(tzinfo=timezone.utc)
    delta_days = (close_dt - datetime.now(timezone.utc)).total_seconds() / 86400
    return 0 <= delta_days <= max_days


class KalshiClient:
    PAGE_LIMIT = 200  # Kalshi /markets cap

    def __init__(self, base_url: str = DEFAULT_BASE, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.dropped_markets = 0

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        last_err: str = ""
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    last_err = "429 rate-limited"
                    log.warning("GET %s: 429 (attempt %d)", url, attempt + 1)
                elif 500 <= r.status_code < 600:
                    last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                    log.warning("GET %s: %s (attempt %d)", url, last_err, attempt + 1)
                else:
                    r.raise_for_status()
                    return r.json()
            except requests.RequestException as e:
                last_err = f"{type(e).__name__}: {e}"
                log.warning("GET %s: %s (attempt %d)", url, last_err, attempt + 1)
            time.sleep(2 ** attempt + random.random() * 0.5)
        raise RuntimeError(f"GET {url} failed after 3 attempts: {last_err}")

    def iter_markets(
        self,
        status: str = "open",
        limit: int = PAGE_LIMIT,
        max_pages: int = 10,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
    ) -> Iterator[dict]:
        cursor: Optional[str] = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"status": status, "limit": min(limit, self.PAGE_LIMIT)}
            if cursor:
                params["cursor"] = cursor
            if event_ticker:
                params["event_ticker"] = event_ticker
            if series_ticker:
                params["series_ticker"] = series_ticker
            data = self._get("/markets", params=params)
            for raw in data.get("markets", []):
                cleaned = _clean_market(raw)
                if cleaned is None:
                    self.dropped_markets += 1
                    continue
                yield cleaned
            cursor = data.get("cursor")
            if not cursor:
                return

    def get_market(self, ticker: str) -> dict:
        return self._get(f"/markets/{ticker}").get("market", {})

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return self._get(
            f"/markets/{ticker}/orderbook", params={"depth": depth}
        ).get("orderbook", {})

    def get_event(self, event_ticker: str) -> dict:
        return self._get(f"/events/{event_ticker}").get("event", {})

    def select_markets(
        self,
        mode: str,
        n: int,
        min_volume: int,
        prior_prices: Optional[dict[str, int]] = None,
        max_pages: int = 10,
        max_days_to_close: Optional[int] = None,
    ) -> list[dict]:
        """Return up to n markets selected per `mode`. Drops missing/malformed entries."""
        if mode not in ("volume", "movers", "illiquid"):
            raise ValueError(f"Unknown selection mode: {mode!r}")
        markets = list(self.iter_markets(status="open", max_pages=max_pages))
        if max_days_to_close is not None:
            markets = [m for m in markets if close_within_days(m, max_days_to_close)]

        if mode == "volume":
            filtered = [m for m in markets if m["volume_24h"] >= min_volume]
            filtered.sort(key=lambda m: m["volume_24h"], reverse=True)
            return filtered[:n]

        if mode == "movers":
            prior = prior_prices or {}
            scored: list[tuple[int, dict]] = []
            for m in markets:
                if m["volume_24h"] < min_volume:
                    continue
                if m["ticker"] in prior:
                    delta = m["yes_ask"] - prior[m["ticker"]]
                else:
                    prev = m.get("previous_yes_ask") or m.get("previous_price") or m["yes_ask"]
                    delta = m["yes_ask"] - prev
                if abs(delta) >= 3:
                    scored.append((abs(delta), m))
            scored.sort(key=lambda t: t[0], reverse=True)
            return [m for _, m in scored[:n]]

        if mode == "illiquid":
            floor = max(1, min_volume // 5)
            scored: list[tuple[int, dict]] = []
            for m in markets:
                spread = m["yes_ask"] - m["yes_bid"]
                if spread >= 5 and m["volume_24h"] >= floor:
                    scored.append((spread, m))
            scored.sort(key=lambda t: t[0], reverse=True)
            return [m for _, m in scored[:n]]

        raise ValueError(f"Unknown selection mode: {mode!r}")


def summarize_orderbook(ob: Any) -> str:
    """Compact textual view of top yes/no order book levels. Robust to malformed input."""
    if not isinstance(ob, dict):
        return "(unavailable)"
    yes = ob.get("yes") if isinstance(ob.get("yes"), list) else []
    no = ob.get("no") if isinstance(ob.get("no"), list) else []

    def fmt(side: list) -> str:
        if not side:
            return "(empty)"
        parts = []
        for entry in side[:5]:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                parts.append(f"{entry[0]}¢×{entry[1]}")
        return ", ".join(parts) if parts else "(empty)"

    return f"YES top: {fmt(yes)} | NO top: {fmt(no)}"
