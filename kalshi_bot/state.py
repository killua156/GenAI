"""Persist per-ticker prior YES asks for the `movers` selection mode."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_prior_prices(path: Path) -> dict[str, int]:
    """Return {ticker: yes_ask} from the state file, or empty if absent/corrupt."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, int] = {}
    for ticker, info in (data.get("tickers") or {}).items():
        if isinstance(info, dict):
            v = info.get("yes_ask")
            if isinstance(v, (int, float)):
                out[ticker] = int(v)
    return out


def save_prior_prices(
    new_prices: dict[str, int],
    path: Path,
    max_entries: int = 500,
) -> None:
    """Merge new prices into the state file, evict oldest beyond max_entries, atomic write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing: dict[str, dict] = {}
    if path.exists():
        try:
            existing = (json.loads(path.read_text()).get("tickers") or {})
        except (json.JSONDecodeError, OSError):
            existing = {}

    for ticker, yes_ask in new_prices.items():
        existing[ticker] = {"yes_ask": int(yes_ask), "updated": now_iso}

    if len(existing) > max_entries:
        sorted_items = sorted(
            existing.items(),
            key=lambda kv: kv[1].get("updated", ""),
            reverse=True,
        )
        existing = dict(sorted_items[:max_entries])

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"tickers": existing}, indent=2, sort_keys=True))
    tmp.replace(path)
