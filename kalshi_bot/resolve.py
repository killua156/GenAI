"""Paper-trade P&L and calibration evaluator.

Walks `reports/*.json`, resolves each pick against Kalshi, computes paper P&L and
Brier score, and writes a summary report. Only touches public Kalshi endpoints —
no auth, no orders.

Usage:
    python resolve.py                        # defaults: reports/ -> reports/EVAL.md + .json
    python resolve.py --only-resolved        # hide pending rows in the detail table
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from kalshi_client import DEFAULT_BASE, KalshiClient

log = logging.getLogger("kalshi_resolve")


@dataclass
class Pick:
    run_id: str
    ticker: str
    title: str
    recommendation: str
    confidence: str
    yes_ask_at_entry: int
    no_ask_at_entry: int
    my_estimate_pct: float
    edge_pp: float


def load_picks(reports_dir: Path) -> list[Pick]:
    picks: list[Pick] = []
    for path in sorted(reports_dir.glob("*.json")):
        if path.name in ("EVAL.json",):
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        run_id = data.get("run_id", path.stem)
        for r in data.get("results") or []:
            picks.append(Pick(
                run_id=run_id,
                ticker=r.get("ticker") or "?",
                title=r.get("title") or "",
                recommendation=(r.get("recommendation") or "").upper(),
                confidence=(r.get("confidence") or "").upper(),
                yes_ask_at_entry=int(r.get("yes_ask") or 0),
                no_ask_at_entry=int(r.get("no_ask") or 0),
                my_estimate_pct=float(r.get("my_estimate_pct") or 50),
                edge_pp=float(r.get("edge_pp") or 0),
            ))
    return picks


def pnl_cents(rec: str, yes_ask: int, no_ask: int, resolved: Optional[str]) -> Optional[int]:
    """Paper P&L in cents from buying 1 contract. None for PASS or unresolved."""
    if resolved not in ("yes", "no"):
        return None
    if rec == "BUY_YES":
        return (100 - yes_ask) if resolved == "yes" else -yes_ask
    if rec == "BUY_NO":
        return (100 - no_ask) if resolved == "no" else -no_ask
    return None


def brier_score(predicted_pct: float, resolved: Optional[str]) -> Optional[float]:
    """Brier for one prediction. None if unresolved."""
    if resolved not in ("yes", "no"):
        return None
    actual = 1.0 if resolved == "yes" else 0.0
    p = max(0.0, min(1.0, predicted_pct / 100.0))
    return (p - actual) ** 2


def _resolution_of(market: dict) -> Optional[str]:
    """Return 'yes', 'no', or None from a Kalshi market dict."""
    result = (market.get("result") or "").lower().strip()
    return result if result in ("yes", "no") else None


def resolve_picks(picks: list[Pick], kalshi: KalshiClient) -> list[dict]:
    cache: dict[str, Optional[str]] = {}
    rows: list[dict] = []
    for p in picks:
        if p.ticker not in cache:
            try:
                m = kalshi.get_market(p.ticker)
                cache[p.ticker] = _resolution_of(m)
            except Exception as e:
                log.warning("failed to resolve %s: %s", p.ticker, e)
                cache[p.ticker] = None
        resolved = cache[p.ticker]
        rows.append({
            "run_id": p.run_id,
            "ticker": p.ticker,
            "title": p.title,
            "recommendation": p.recommendation,
            "confidence": p.confidence,
            "yes_ask_at_entry": p.yes_ask_at_entry,
            "no_ask_at_entry": p.no_ask_at_entry,
            "my_estimate_pct": p.my_estimate_pct,
            "edge_pp": p.edge_pp,
            "resolved": resolved,
            "pnl_cents": pnl_cents(p.recommendation, p.yes_ask_at_entry, p.no_ask_at_entry, resolved),
            "brier": brier_score(p.my_estimate_pct, resolved),
        })
    return rows


def summarize(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    buys = [r for r in rows if r["recommendation"] in ("BUY_YES", "BUY_NO")]
    resolved_buys = [r for r in buys if r["resolved"] is not None]
    wins = [r for r in resolved_buys if (r["pnl_cents"] or 0) > 0]
    total_pnl = sum((r["pnl_cents"] or 0) for r in resolved_buys)

    resolved_all = [r for r in rows if r["brier"] is not None]
    brier = sum(r["brier"] for r in resolved_all) / len(resolved_all) if resolved_all else None

    by_conf: dict[str, dict] = {}
    for conf in ("LOW", "MEDIUM", "HIGH"):
        bucket = [r for r in resolved_buys if r["confidence"] == conf]
        wins_b = [r for r in bucket if (r["pnl_cents"] or 0) > 0]
        by_conf[conf] = {
            "n_picks": len(bucket),
            "n_wins": len(wins_b),
            "win_rate": (len(wins_b) / len(bucket)) if bucket else None,
            "total_pnl_cents": sum((r["pnl_cents"] or 0) for r in bucket),
        }

    return {
        "total_picks": len(rows),
        "total_buys": len(buys),
        "resolved_buys": len(resolved_buys),
        "unresolved_buys": len(buys) - len(resolved_buys),
        "n_wins": len(wins),
        "n_losses": len(resolved_buys) - len(wins),
        "win_rate": (len(wins) / len(resolved_buys)) if resolved_buys else None,
        "total_pnl_cents": total_pnl,
        "mean_pnl_per_pick_cents": (total_pnl / len(resolved_buys)) if resolved_buys else None,
        "brier_score": brier,
        "brier_sample_size": len(resolved_all),
        "by_confidence": by_conf,
    }


def render_markdown(summary: dict, rows: list[dict], now_iso: str) -> str:
    out = [
        "# Kalshi Bot — Evaluation Report",
        f"_Generated {now_iso}_",
        "",
        "## Overall",
        "",
        f"- Total picks: {summary['total_picks']}",
        f"- BUY picks: {summary['total_buys']} "
        f"(resolved: {summary['resolved_buys']}, pending: {summary['unresolved_buys']})",
    ]
    if summary["win_rate"] is not None:
        out += [
            f"- Hit rate: {summary['n_wins']}/{summary['resolved_buys']} = **{summary['win_rate']:.1%}**",
            f"- Total paper P&L: **{summary['total_pnl_cents']:+d}¢** across resolved BUYs",
            f"- Mean P&L per BUY: **{summary['mean_pnl_per_pick_cents']:+.1f}¢**",
        ]
    else:
        out.append("- No resolved BUYs yet.")
    if summary["brier_score"] is not None:
        out += [
            f"- Brier score (n={summary['brier_sample_size']} resolved picks incl. PASS): "
            f"**{summary['brier_score']:.3f}** _(0.25 = 'always 50%'; lower is better)_",
        ]

    out += ["", "## By confidence", "",
            "| Confidence | BUYs | Wins | Hit rate | P&L (¢) |",
            "|---|---|---|---|---|"]
    for conf in ("HIGH", "MEDIUM", "LOW"):
        b = summary["by_confidence"][conf]
        wr = f"{b['win_rate']:.0%}" if b["win_rate"] is not None else "—"
        out.append(f"| {conf} | {b['n_picks']} | {b['n_wins']} | {wr} | {b['total_pnl_cents']:+d} |")

    out += ["", "## Detail", "",
            "| Run | Ticker | Rec | Conf | Entry (YES/NO ask) | Resolved | P&L (¢) | Brier |",
            "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        entry = f"{r['yes_ask_at_entry']}¢ / {r['no_ask_at_entry']}¢"
        resolved = r["resolved"] or "pending"
        pnl = f"{r['pnl_cents']:+d}" if r["pnl_cents"] is not None else "—"
        brier = f"{r['brier']:.3f}" if r["brier"] is not None else "—"
        run_short = r["run_id"][:10] if r["run_id"] else "?"
        out.append(
            f"| {run_short} | `{r['ticker']}` | {r['recommendation']} | "
            f"{r['confidence']} | {entry} | {resolved} | {pnl} | {brier} |"
        )
    return "\n".join(out) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Paper-trade P&L + calibration evaluator")
    p.add_argument("--reports-dir", default="reports",
                   help="Directory containing bot report JSON files")
    p.add_argument("--output", default="reports/EVAL.md",
                   help="Markdown output path")
    p.add_argument("--json-output", default="reports/EVAL.json",
                   help="JSON output path")
    p.add_argument("--only-resolved", action="store_true",
                   help="Omit pending picks from the detail table")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    reports_dir = Path(args.reports_dir)
    if not reports_dir.exists():
        print(f"ERROR: reports directory not found: {reports_dir}", file=sys.stderr)
        return 1

    picks = load_picks(reports_dir)
    if not picks:
        print(f"No picks found in {reports_dir}/*.json", file=sys.stderr)
        return 1

    print(f"Loaded {len(picks)} picks from {reports_dir}; resolving against Kalshi...")
    kalshi = KalshiClient(DEFAULT_BASE)
    rows = resolve_picks(picks, kalshi)

    if args.only_resolved:
        rows_display = [r for r in rows if r["resolved"] is not None]
    else:
        rows_display = rows

    summary = summarize(rows)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    md = render_markdown(summary, rows_display, now_iso)
    out_md = Path(args.output)
    out_json = Path(args.json_output)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md)
    out_json.write_text(json.dumps(
        {"summary": summary, "rows": rows, "generated_utc": now_iso},
        indent=2,
    ))

    print("\n" + md)
    print(f"Wrote {out_md} and {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
