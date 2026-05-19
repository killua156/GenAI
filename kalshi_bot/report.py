"""Markdown report generation and recommendation parsing."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

CONFIDENCE_SCORE = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

_REC_RE = re.compile(r"\*\*Recommendation:\*\*\s*([A-Z][A-Z ]*?)\s*(?:\n|$)")
_CONF_RE = re.compile(r"\*\*Confidence:\*\*\s*([A-Za-z]+)")
_EST_RE = re.compile(r"\*\*My estimate:\*\*\s*(-?\d+(?:\.\d+)?)\s*%")
_IMP_RE = re.compile(r"\*\*Market implied:\*\*\s*(-?\d+(?:\.\d+)?)\s*%")
_EDGE_RE = re.compile(r"\*\*Edge:\*\*\s*([+\-]?\d+(?:\.\d+)?)")


def parse_recommendation(text: str) -> dict:
    out: dict = {}
    if m := _REC_RE.search(text):
        out["recommendation"] = m.group(1).strip()
    if m := _CONF_RE.search(text):
        out["confidence"] = m.group(1).strip().upper()
    if m := _EST_RE.search(text):
        out["my_estimate"] = float(m.group(1))
    if m := _IMP_RE.search(text):
        out["market_implied"] = float(m.group(1))
    if m := _EDGE_RE.search(text):
        out["edge_pp"] = float(m.group(1))
    return out


def _is_actionable(result: dict) -> bool:
    rec = (result.get("recommendation") or "").upper()
    return rec.startswith("BUY")


def _sort_key(r: dict) -> tuple:
    conf = CONFIDENCE_SCORE.get((r.get("confidence") or "").upper(), 0)
    edge = abs(r.get("edge_pp") or 0)
    return (conf, edge)


def write_report(results: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    path = output_dir / f"{date_str}.md"

    actionable = [r for r in results if _is_actionable(r)]
    actionable.sort(key=_sort_key, reverse=True)

    lines = [
        f"# Kalshi Bot Report — {date_str}",
        f"_Generated {now.strftime('%Y-%m-%d %H:%M:%S')} UTC. {len(results)} markets analyzed; "
        f"{len(actionable)} actionable._",
        "",
        "> Educational/research output. Not financial advice. Verify before trading.",
        "",
    ]

    if actionable:
        lines += ["## Actionable picks", ""]
        for r in actionable:
            lines += [
                f"### {r['title']}",
                (
                    f"`{r['ticker']}` · YES {r['yes_ask']}¢ / NO {r['no_ask']}¢ · "
                    f"vol24h {r.get('volume_24h', 0):,}"
                ),
                "",
                r["analysis"],
                "",
                "---",
                "",
            ]
    else:
        lines += ["## Actionable picks", "", "_No clear edges identified today._", ""]

    lines += ["## All markets reviewed", ""]
    for r in results:
        rec = r.get("recommendation") or "—"
        conf = r.get("confidence") or ""
        edge = r.get("edge_pp")
        edge_s = f"{edge:+.0f}pp" if edge is not None else ""
        lines.append(
            f"- `{r['ticker']}` — {r['title']} · **{rec}** {conf} {edge_s}".rstrip()
        )

    path.write_text("\n".join(lines) + "\n")
    return path
