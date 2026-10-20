import json
from unittest.mock import MagicMock

from resolve import (
    Pick,
    brier_score,
    load_picks,
    pnl_cents,
    resolve_picks,
    summarize,
)


# ---- pnl_cents ----

def test_pnl_buy_yes_resolves_yes():
    assert pnl_cents("BUY_YES", 60, 40, "yes") == 40


def test_pnl_buy_yes_resolves_no():
    assert pnl_cents("BUY_YES", 60, 40, "no") == -60


def test_pnl_buy_no_resolves_no():
    assert pnl_cents("BUY_NO", 60, 40, "no") == 60


def test_pnl_buy_no_resolves_yes():
    assert pnl_cents("BUY_NO", 60, 40, "yes") == -40


def test_pnl_pass_is_none():
    assert pnl_cents("PASS", 60, 40, "yes") is None


def test_pnl_unresolved_is_none():
    assert pnl_cents("BUY_YES", 60, 40, None) is None


# ---- brier_score ----

def test_brier_perfect_prediction_yes():
    assert brier_score(100, "yes") == 0.0


def test_brier_perfect_prediction_no():
    assert brier_score(0, "no") == 0.0


def test_brier_worst_prediction():
    assert brier_score(100, "no") == 1.0


def test_brier_coin_flip():
    assert brier_score(50, "yes") == 0.25
    assert brier_score(50, "no") == 0.25


def test_brier_unresolved_is_none():
    assert brier_score(70, None) is None


def test_brier_clamps_out_of_range():
    assert brier_score(150, "yes") == 0.0  # clamped to 100
    assert brier_score(-20, "no") == 0.0   # clamped to 0


# ---- load_picks ----

def test_load_picks_reads_json_files(tmp_path):
    report = {
        "run_id": "2026-10-15_120000",
        "results": [
            {
                "ticker": "KX-A", "title": "A", "yes_ask": 60, "no_ask": 40,
                "recommendation": "BUY_YES", "confidence": "HIGH",
                "my_estimate_pct": 75, "edge_pp": 15,
            },
            {
                "ticker": "KX-B", "title": "B", "yes_ask": 50, "no_ask": 50,
                "recommendation": "PASS", "confidence": "LOW",
                "my_estimate_pct": 51, "edge_pp": 1,
            },
        ],
    }
    (tmp_path / "2026-10-15_120000.json").write_text(json.dumps(report))

    picks = load_picks(tmp_path)
    assert len(picks) == 2
    assert picks[0].ticker == "KX-A"
    assert picks[0].recommendation == "BUY_YES"
    assert picks[0].yes_ask_at_entry == 60
    assert picks[1].recommendation == "PASS"


def test_load_picks_skips_eval_json(tmp_path):
    (tmp_path / "run.json").write_text(json.dumps({
        "run_id": "r", "results": [{"ticker": "KX-A", "yes_ask": 50, "no_ask": 50}]
    }))
    (tmp_path / "EVAL.json").write_text(json.dumps({"summary": {}, "rows": []}))
    assert len(load_picks(tmp_path)) == 1


def test_load_picks_handles_corrupt_file(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps({
        "run_id": "r", "results": [{"ticker": "KX-A", "yes_ask": 50, "no_ask": 50}]
    }))
    (tmp_path / "bad.json").write_text("not json")
    picks = load_picks(tmp_path)
    assert len(picks) == 1


# ---- resolve_picks ----

def _pick(**kw):
    base = dict(
        run_id="r", ticker="KX-A", title="A",
        recommendation="BUY_YES", confidence="MEDIUM",
        yes_ask_at_entry=60, no_ask_at_entry=40,
        my_estimate_pct=70, edge_pp=10,
    )
    base.update(kw)
    return Pick(**base)


def test_resolve_picks_caches_per_ticker():
    kalshi = MagicMock()
    kalshi.get_market.return_value = {"result": "yes"}

    picks = [_pick(ticker="KX-A"), _pick(ticker="KX-A", run_id="r2"), _pick(ticker="KX-B")]
    rows = resolve_picks(picks, kalshi)

    assert kalshi.get_market.call_count == 2  # one per unique ticker
    assert all(r["resolved"] == "yes" for r in rows)


def test_resolve_picks_marks_unsettled_as_none():
    kalshi = MagicMock()
    kalshi.get_market.return_value = {"result": ""}  # not yet settled

    rows = resolve_picks([_pick()], kalshi)
    assert rows[0]["resolved"] is None
    assert rows[0]["pnl_cents"] is None
    assert rows[0]["brier"] is None


def test_resolve_picks_handles_fetch_error():
    kalshi = MagicMock()
    kalshi.get_market.side_effect = RuntimeError("network down")

    rows = resolve_picks([_pick()], kalshi)
    assert rows[0]["resolved"] is None


# ---- summarize ----

def test_summarize_mixed_outcomes():
    rows = [
        # 2 winning BUYs, 1 losing BUY, 1 PASS
        {"recommendation": "BUY_YES", "confidence": "HIGH",
         "yes_ask_at_entry": 60, "no_ask_at_entry": 40,
         "my_estimate_pct": 70, "resolved": "yes", "pnl_cents": 40, "brier": 0.09, "run_id": "r", "ticker": "KX-A", "title": "A", "edge_pp": 10},
        {"recommendation": "BUY_NO", "confidence": "MEDIUM",
         "yes_ask_at_entry": 70, "no_ask_at_entry": 30,
         "my_estimate_pct": 20, "resolved": "no", "pnl_cents": 70, "brier": 0.04, "run_id": "r", "ticker": "KX-B", "title": "B", "edge_pp": -10},
        {"recommendation": "BUY_YES", "confidence": "LOW",
         "yes_ask_at_entry": 55, "no_ask_at_entry": 45,
         "my_estimate_pct": 60, "resolved": "no", "pnl_cents": -55, "brier": 0.36, "run_id": "r", "ticker": "KX-C", "title": "C", "edge_pp": 5},
        {"recommendation": "PASS", "confidence": "LOW",
         "yes_ask_at_entry": 50, "no_ask_at_entry": 50,
         "my_estimate_pct": 50, "resolved": "yes", "pnl_cents": None, "brier": 0.25, "run_id": "r", "ticker": "KX-D", "title": "D", "edge_pp": 0},
    ]
    s = summarize(rows)
    assert s["total_picks"] == 4
    assert s["total_buys"] == 3
    assert s["resolved_buys"] == 3
    assert s["n_wins"] == 2
    assert s["n_losses"] == 1
    assert s["total_pnl_cents"] == 40 + 70 - 55  # 55
    assert abs(s["win_rate"] - 2 / 3) < 1e-9
    # Brier includes PASS
    assert s["brier_sample_size"] == 4


def test_summarize_handles_no_resolved():
    rows = [{"recommendation": "BUY_YES", "confidence": "HIGH",
             "yes_ask_at_entry": 60, "no_ask_at_entry": 40,
             "my_estimate_pct": 70, "resolved": None, "pnl_cents": None, "brier": None,
             "run_id": "r", "ticker": "KX-A", "title": "A", "edge_pp": 10}]
    s = summarize(rows)
    assert s["resolved_buys"] == 0
    assert s["win_rate"] is None
    assert s["mean_pnl_per_pick_cents"] is None
    assert s["brier_score"] is None


def test_summarize_bucket_by_confidence():
    rows = [
        {"recommendation": "BUY_YES", "confidence": "HIGH", "yes_ask_at_entry": 60, "no_ask_at_entry": 40,
         "my_estimate_pct": 70, "resolved": "yes", "pnl_cents": 40, "brier": 0.09,
         "run_id": "r", "ticker": "A", "title": "A", "edge_pp": 10},
        {"recommendation": "BUY_YES", "confidence": "HIGH", "yes_ask_at_entry": 55, "no_ask_at_entry": 45,
         "my_estimate_pct": 65, "resolved": "yes", "pnl_cents": 45, "brier": 0.12,
         "run_id": "r", "ticker": "B", "title": "B", "edge_pp": 10},
        {"recommendation": "BUY_YES", "confidence": "LOW", "yes_ask_at_entry": 50, "no_ask_at_entry": 50,
         "my_estimate_pct": 55, "resolved": "no", "pnl_cents": -50, "brier": 0.30,
         "run_id": "r", "ticker": "C", "title": "C", "edge_pp": 5},
    ]
    s = summarize(rows)
    assert s["by_confidence"]["HIGH"]["n_picks"] == 2
    assert s["by_confidence"]["HIGH"]["n_wins"] == 2
    assert s["by_confidence"]["HIGH"]["win_rate"] == 1.0
    assert s["by_confidence"]["LOW"]["n_wins"] == 0
    assert s["by_confidence"]["LOW"]["win_rate"] == 0.0
    assert s["by_confidence"]["MEDIUM"]["n_picks"] == 0
    assert s["by_confidence"]["MEDIUM"]["win_rate"] is None
