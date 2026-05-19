"""Thin client for Kalshi's public REST endpoints."""
from __future__ import annotations

import time
from typing import Any, Iterator, Optional

import requests

DEFAULT_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiClient:
    def __init__(self, base_url: str = DEFAULT_BASE, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                last_err = e
                time.sleep(1 + attempt)
        raise RuntimeError(f"GET {url} failed: {last_err}")

    def iter_markets(
        self,
        status: str = "open",
        limit: int = 200,
        max_pages: int = 10,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
    ) -> Iterator[dict]:
        cursor: Optional[str] = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"status": status, "limit": min(limit, 200)}
            if cursor:
                params["cursor"] = cursor
            if event_ticker:
                params["event_ticker"] = event_ticker
            if series_ticker:
                params["series_ticker"] = series_ticker
            data = self._get("/markets", params=params)
            for m in data.get("markets", []):
                yield m
            cursor = data.get("cursor")
            if not cursor:
                return

    def get_market(self, ticker: str) -> dict:
        return self._get(f"/markets/{ticker}").get("market", {})

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return self._get(f"/markets/{ticker}/orderbook", params={"depth": depth}).get(
            "orderbook", {}
        )

    def get_event(self, event_ticker: str) -> dict:
        return self._get(f"/events/{event_ticker}").get("event", {})

    def top_markets_by_volume(
        self,
        n: int = 20,
        min_volume_24h: int = 1000,
        max_pages: int = 10,
    ) -> list[dict]:
        candidates: list[dict] = []
        for m in self.iter_markets(status="open", limit=200, max_pages=max_pages):
            if m.get("volume_24h", 0) >= min_volume_24h:
                candidates.append(m)
        candidates.sort(key=lambda m: m.get("volume_24h", 0), reverse=True)
        return candidates[:n]


def summarize_orderbook(ob: dict) -> str:
    """Compact textual view of yes/no order book sides."""
    yes = ob.get("yes") or []
    no = ob.get("no") or []
    def fmt(side: list) -> str:
        if not side:
            return "(empty)"
        return ", ".join(f"{price}¢×{size}" for price, size in side[:5])
    return f"YES top: {fmt(yes)} | NO top: {fmt(no)}"
