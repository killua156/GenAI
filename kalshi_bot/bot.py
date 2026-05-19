"""Kalshi betting bot — fetches markets, analyzes with Claude + web search, writes report."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from analyzer import Analyzer, DEFAULT_MODEL
from kalshi_client import DEFAULT_BASE, KalshiClient, summarize_orderbook
from report import parse_recommendation, write_report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily Kalshi bet analyzer")
    p.add_argument("--top", type=int, default=10, help="Markets to analyze (default 10)")
    p.add_argument("--min-volume", type=int, default=1000, help="Min 24h volume filter")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Claude model id")
    p.add_argument("--max-searches", type=int, default=5, help="Web searches per market")
    p.add_argument("--output-dir", default="reports", help="Where to write the report")
    p.add_argument("--event", default=None, help="Filter to a single event ticker")
    p.add_argument("--series", default=None, help="Filter to a single series ticker")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List the markets that would be analyzed and exit",
    )
    return p.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    if not args.dry_run and not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. Add it to .env or export it, "
            "or pass --dry-run to skip LLM analysis.",
            file=sys.stderr,
        )
        return 1

    base = os.getenv("KALSHI_API_BASE", DEFAULT_BASE)
    kalshi = KalshiClient(base)

    print(f"Fetching Kalshi markets from {base} ...")
    if args.event or args.series:
        markets = [
            m
            for m in kalshi.iter_markets(
                status="open",
                limit=200,
                max_pages=5,
                event_ticker=args.event,
                series_ticker=args.series,
            )
            if m.get("volume_24h", 0) >= args.min_volume
        ]
        markets.sort(key=lambda m: m.get("volume_24h", 0), reverse=True)
        markets = markets[: args.top]
    else:
        markets = kalshi.top_markets_by_volume(
            n=args.top, min_volume_24h=args.min_volume
        )

    if not markets:
        print("No markets matched the filters. Try lowering --min-volume.")
        return 0

    print(f"Selected {len(markets)} markets:")
    for m in markets:
        print(
            f"  {m['ticker']:<32} vol24h={m.get('volume_24h', 0):>8,}  "
            f"YES={m.get('yes_ask')}¢  {m.get('title','')[:60]}"
        )

    if args.dry_run:
        return 0

    analyzer = Analyzer(model=args.model, max_searches=args.max_searches)
    results: list[dict] = []
    for i, m in enumerate(markets, 1):
        title = (m.get("title") or "")[:70]
        print(f"\n[{i}/{len(markets)}] {m['ticker']}  {title}")
        ob_summary = None
        try:
            ob = kalshi.get_orderbook(m["ticker"])
            ob_summary = summarize_orderbook(ob)
        except Exception as e:
            print(f"  orderbook fetch failed: {e}")
        try:
            analysis = analyzer.analyze(m, ob_summary)
        except Exception as e:
            print(f"  ANALYSIS FAILED: {e}")
            continue
        parsed = parse_recommendation(analysis)
        rec = parsed.get("recommendation", "?")
        conf = parsed.get("confidence", "?")
        edge = parsed.get("edge_pp")
        edge_s = f" edge={edge:+.0f}pp" if edge is not None else ""
        print(f"  -> {rec} ({conf}){edge_s}")
        results.append(
            {
                "ticker": m["ticker"],
                "title": m.get("title", ""),
                "yes_ask": m.get("yes_ask"),
                "no_ask": m.get("no_ask"),
                "volume_24h": m.get("volume_24h", 0),
                "analysis": analysis,
                **parsed,
            }
        )

    path = write_report(results, Path(args.output_dir))
    print(f"\nReport written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
