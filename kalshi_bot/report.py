"""Markdown + JSON report generation, plus JSONL append/read for atomicity."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CONFIDENCE_SCORE = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

_REC_LABELS = {"BUY_YES": "BUY YES", "BUY_NO": "BUY NO", "PASS": "PASS"}


def is_actionable(result: dict) -> bool:
    return (result.get("recommendation") or "").upper() in ("BUY_YES", "BUY_NO")


def _sort_key(r: dict) -> tuple:
    conf = CONFIDENCE_SCORE.get((r.get("confidence") or "").upper(), 0)
    try:
        edge = abs(float(r.get("edge_pp") or 0))
    except (TypeError, ValueError):
        edge = 0
    return (conf, edge)


def _rec_label(rec: Optional[str]) -> str:
    return _REC_LABELS.get((rec or "").upper(), rec or "—")


def _fmt_pct(v) -> str:
    try:
        return f"{float(v):.0f}%"
    except (TypeError, ValueError):
        return "?"


def _fmt_edge(v) -> str:
    try:
        return f"{float(v):+.0f}pp"
    except (TypeError, ValueError):
        return "?"


def write_outputs(
    results: list[dict],
    output_dir: Path,
    run_id: str,
    cost_actual: Optional[float] = None,
) -> tuple[Path, Path]:
    """Write `{run_id}.md` and `{run_id}.json` into output_dir. Returns (md_path, json_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{run_id}.md"
    json_path = output_dir / f"{run_id}.json"

    json_path.write_text(json.dumps({
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_markets": len(results),
        "cost_actual_usd": cost_actual,
        "results": results,
    }, indent=2))

    md_path.write_text(_render_markdown(results, run_id, cost_actual))
    return md_path, json_path


def _render_markdown(results: list[dict], run_id: str, cost_actual: Optional[float]) -> str:
    actionable = [r for r in results if is_actionable(r)]
    actionable.sort(key=_sort_key, reverse=True)

    out: list[str] = [
        f"# Kalshi Bot Report — {run_id}",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC. "
        f"{len(results)} markets analyzed; {len(actionable)} actionable."
        + (f" Cost: ${cost_actual:.2f}._" if cost_actual is not None else "_"),
        "",
        "> Educational/research output. Not financial advice. Verify before trading.",
        "",
    ]

    if actionable:
        out += ["## Actionable picks", ""]
        for r in actionable:
            out += _render_actionable(r) + ["", "---", ""]
    else:
        out += ["## Actionable picks", "", "_No clear edges identified this run._", ""]

    out += ["## All markets reviewed", ""]
    for r in results:
        line = (
            f"- `{r.get('ticker','?')}` — {r.get('title','?')} · "
            f"**{_rec_label(r.get('recommendation'))}**"
        )
        conf = r.get("confidence")
        if conf:
            line += f" {conf}"
        edge = r.get("edge_pp")
        if edge is not None:
            try:
                line += f" {float(edge):+.0f}pp"
            except (TypeError, ValueError):
                pass
        out.append(line)
    return "\n".join(out) + "\n"


def _render_actionable(r: dict) -> list[str]:
    vol = r.get("volume_24h") or 0
    try:
        vol_str = f"{int(vol):,}"
    except (TypeError, ValueError):
        vol_str = "?"
    lines = [
        f"### {r.get('title','?')}",
        f"`{r.get('ticker','?')}` · YES {r.get('yes_ask','?')}¢ / NO {r.get('no_ask','?')}¢ · "
        f"vol24h {vol_str}",
        "",
        f"**Recommendation:** {_rec_label(r.get('recommendation'))}  "
        f"**Confidence:** {r.get('confidence','?')}  "
        f"**Edge:** {_fmt_edge(r.get('edge_pp'))}",
        f"**My estimate:** {_fmt_pct(r.get('my_estimate_pct'))}  "
        f"**Market implied:** {_fmt_pct(r.get('market_implied_pct'))}",
        "",
        f"{r.get('reasoning','(no reasoning)')}",
    ]
    sources = r.get("key_sources") or []
    if sources:
        lines += ["", "**Sources:**"] + [f"- {s}" for s in sources]
    return lines


# ---- JSONL incremental persistence ----

def append_partial(path: Path, result: dict) -> None:
    """Append one analysis result as a single JSON line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(result) + "\n")


def read_partial(path: Path) -> list[dict]:
    """Read a JSONL file back into a list of dicts. Skips malformed lines silently."""
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
