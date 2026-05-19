import json

from report import append_partial, read_partial, write_outputs


def test_write_outputs_empty(tmp_path):
    md, j = write_outputs([], tmp_path, "test-run")
    assert md.exists() and j.exists()
    assert "No clear edges" in md.read_text()
    data = json.loads(j.read_text())
    assert data["n_markets"] == 0
    assert data["results"] == []


def test_write_outputs_mixed(tmp_path):
    results = [
        {
            "ticker": "KX-A", "title": "Will A?", "yes_ask": 60, "no_ask": 40, "volume_24h": 5000,
            "recommendation": "BUY_YES", "confidence": "HIGH", "edge_pp": 15,
            "my_estimate_pct": 75, "market_implied_pct": 60,
            "reasoning": "A is likely.", "key_sources": ["https://a.example"],
        },
        {
            "ticker": "KX-B", "title": "Will B?", "yes_ask": 50, "no_ask": 50, "volume_24h": 2000,
            "recommendation": "PASS", "confidence": "LOW", "edge_pp": 2,
            "my_estimate_pct": 52, "market_implied_pct": 50,
            "reasoning": "No edge.", "key_sources": [],
        },
        {
            "ticker": "KX-C", "title": "Will C?", "yes_ask": 30, "no_ask": 70, "volume_24h": 8000,
            "recommendation": "BUY_NO", "confidence": "MEDIUM", "edge_pp": -10,
            "my_estimate_pct": 20, "market_implied_pct": 30,
            "reasoning": "C unlikely.", "key_sources": ["https://c.example"],
        },
    ]
    md, j = write_outputs(results, tmp_path, "test-run", cost_actual=0.42)
    md_text = md.read_text()
    # Actionable ordering: HIGH+15 first, MEDIUM+10 second, PASS not in actionable section
    a_pos = md_text.find("Will A?")
    c_pos = md_text.find("Will C?")
    actionable_section_end = md_text.find("## All markets reviewed")
    assert a_pos < c_pos < actionable_section_end
    assert "$0.42" in md_text
    data = json.loads(j.read_text())
    assert data["cost_actual_usd"] == 0.42
    assert len(data["results"]) == 3


def test_write_outputs_missing_fields(tmp_path):
    results = [{
        "ticker": "KX-X", "title": "Will X?", "yes_ask": 50, "no_ask": 50, "volume_24h": 0,
        "recommendation": "PASS", "confidence": "LOW",
        # edge_pp, reasoning, key_sources missing
    }]
    md, _ = write_outputs(results, tmp_path, "test-run")
    assert "KX-X" in md.read_text()


def test_write_outputs_all_pass(tmp_path):
    results = [{
        "ticker": "KX-Z", "title": "Will Z?", "yes_ask": 50, "no_ask": 50, "volume_24h": 1000,
        "recommendation": "PASS", "confidence": "LOW", "edge_pp": 0,
    }]
    md, _ = write_outputs(results, tmp_path, "test-run")
    text = md.read_text()
    assert "No clear edges" in text
    assert "KX-Z" in text  # still appears in all-markets section


def test_partial_jsonl_roundtrip(tmp_path):
    p = tmp_path / "partial.jsonl"
    rows = [{"a": 1}, {"b": 2, "nested": [1, 2]}]
    for r in rows:
        append_partial(p, r)
    assert read_partial(p) == rows


def test_partial_jsonl_skips_malformed(tmp_path):
    p = tmp_path / "partial.jsonl"
    p.write_text('{"a":1}\ngarbage line\n\n{"b":2}\n')
    assert read_partial(p) == [{"a": 1}, {"b": 2}]
