"""Kalshi betting bot — fetches markets, analyzes with Claude + web search, writes report."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from analyzer import Analyzer, DEFAULT_MODEL
from costs import estimate as estimate_cost, from_usage
from kalshi_client import DEFAULT_BASE, KalshiClient, summarize_orderbook
from report import append_partial, read_partial, write_outputs
from state import load_prior_prices, save_prior_prices

DEFAULT_OUTPUT_DIR = "reports"
DEFAULT_STATE_FILE = "state/last_prices.json"

log = logging.getLogger("kalshi_bot")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily Kalshi bet analyzer")
    p.add_argument("--mode", choices=("volume", "movers", "illiquid"), default="volume",
                   help="Selection strategy when --event/--series not set")
    p.add_argument("--top", type=int, default=10, help="Markets to analyze (default 10)")
    p.add_argument("--min-volume", type=int, default=1000, help="Min 24h volume filter")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Claude model id")
    p.add_argument("--max-searches", type=int, default=5, help="Web searches per market")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Where to write reports")
    p.add_argument("--state-file", default=DEFAULT_STATE_FILE,
                   help="Where to read/write prior prices for movers mode")
    p.add_argument("--event", default=None, help="Filter to a single event ticker")
    p.add_argument("--series", default=None, help="Filter to a single series ticker")
    p.add_argument("--max-cost", type=float, default=5.0,
                   help="Hard cap on estimated USD spend per run (default $5)")
    p.add_argument("--no-prompt", action="store_true",
                   help="Skip interactive cost confirmation (for cron)")
    p.add_argument("--resume", default=None,
                   help="Path to a partial JSONL file to regenerate a report from")
    p.add_argument("--dry-run", action="store_true",
                   help="List the markets that would be analyzed and exit")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.resume:
        return _resume(Path(args.resume), output_dir)

    if not args.dry_run and not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. Add it to .env or export it, "
            "or pass --dry-run to skip LLM analysis.",
            file=sys.stderr,
        )
        return 1

    base = os.getenv("KALSHI_API_BASE", DEFAULT_BASE)
    kalshi = KalshiClient(base)
    state_file = Path(args.state_file)
    prior_prices = load_prior_prices(state_file)

    print(f"Fetching Kalshi markets from {base} (mode={args.mode}) ...")

    if args.event or args.series:
        if args.mode != "volume":
            print(f"Note: --event/--series specified; --mode {args.mode!r} ignored.")
        all_markets = [
            m for m in kalshi.iter_markets(
                status="open",
                event_ticker=args.event,
                series_ticker=args.series,
            )
            if m["volume_24h"] >= args.min_volume
        ]
        all_markets.sort(key=lambda m: m["volume_24h"], reverse=True)
        markets = all_markets[: args.top]
    else:
        markets = kalshi.select_markets(
            mode=args.mode,
            n=args.top,
            min_volume=args.min_volume,
            prior_prices=prior_prices,
        )

    if kalshi.dropped_markets:
        log.info("Dropped %d markets with missing required fields.", kalshi.dropped_markets)

    if not markets:
        print("No markets matched. Try lowering --min-volume or switching --mode.")
        return 0

    print(f"\nSelected {len(markets)} markets:")
    for m in markets:
        spread = m["yes_ask"] - m["yes_bid"]
        title = (m.get("title") or "")[:50]
        print(
            f"  {m['ticker']:<34} vol24h={m['volume_24h']:>8,}  "
            f"YES={m['yes_ask']:>3}¢ spread={spread:>2}¢  {title}"
        )

    if args.dry_run:
        return 0

    est = estimate_cost(len(markets), args.model, args.max_searches)
    print(
        f"\nEstimated cost: ${est:.2f} (cap ${args.max_cost:.2f}). "
        f"Model: {args.model}. Up to {args.max_searches} searches/market."
    )
    if est > args.max_cost:
        print(f"REFUSING: estimated ${est:.2f} exceeds --max-cost ${args.max_cost:.2f}.",
              file=sys.stderr)
        return 2
    if sys.stdin.isatty() and not args.no_prompt:
        if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 0

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    partial_path = output_dir / ".partial" / f"{run_id}.jsonl"

    analyzer = Analyzer(model=args.model, max_searches=args.max_searches)
    results: list[dict] = []
    fail_count = 0
    for i, m in enumerate(markets, 1):
        title = (m.get("title") or "")[:60]
        print(f"\n[{i}/{len(markets)}] {m['ticker']}  {title}")
        ob_summary = None
        try:
            ob_summary = summarize_orderbook(kalshi.get_orderbook(m["ticker"]))
        except Exception as e:
            log.warning("orderbook fetch failed for %s: %s", m["ticker"], e)
        try:
            analysis = analyzer.analyze(m, ob_summary)
        except Exception as e:
            log.exception("analyzer crashed on %s: %s", m["ticker"], e)
            fail_count += 1
            continue

        result = {
            "ticker": m["ticker"],
            "title": m.get("title", ""),
            "yes_ask": m["yes_ask"],
            "no_ask": m["no_ask"],
            "yes_bid": m["yes_bid"],
            "no_bid": m["no_bid"],
            "volume_24h": m["volume_24h"],
            "event_ticker": m.get("event_ticker"),
            "category": m.get("category"),
            **{k: v for k, v in analysis.items() if k != "_usage"},
            "_usage": analysis.get("_usage", {}),
        }
        append_partial(partial_path, result)
        results.append(result)
        print(
            f"  -> {result.get('recommendation')} ({result.get('confidence')}) "
            f"edge={result.get('edge_pp')}pp"
        )

    cost_total = sum(from_usage(r.get("_usage") or {}, args.model) for r in results)
    md_path, json_path = write_outputs(results, output_dir, run_id, cost_actual=cost_total)

    if results:
        save_prior_prices(
            {r["ticker"]: int(r["yes_ask"]) for r in results if r.get("yes_ask") is not None},
            state_file,
        )

    if partial_path.exists():
        partial_path.unlink()

    print(f"\nReport: {md_path}")
    print(f"JSON:   {json_path}")
    print(
        f"Done. {len(results)} markets analyzed, {fail_count} failed, "
        f"actual cost ~${cost_total:.2f}."
    )
    return 0


def _resume(partial_path: Path, output_dir: Path) -> int:
    if not partial_path.exists():
        print(f"ERROR: partial file not found: {partial_path}", file=sys.stderr)
        return 1
    results = read_partial(partial_path)
    if not results:
        print(f"ERROR: partial file is empty or malformed: {partial_path}", file=sys.stderr)
        return 1
    run_id = partial_path.stem
    print(f"Resuming from {partial_path}: {len(results)} markets")
    md_path, json_path = write_outputs(results, output_dir, run_id, cost_actual=None)
    partial_path.unlink()
    print(f"Wrote {md_path} and {json_path}; deleted partial.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
