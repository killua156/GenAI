import json

from state import load_prior_prices, save_prior_prices


def test_load_missing_file(tmp_path):
    assert load_prior_prices(tmp_path / "nope.json") == {}


def test_load_corrupt_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not json")
    assert load_prior_prices(p) == {}


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    save_prior_prices({"KX-A": 60, "KX-B": 40}, p)
    assert load_prior_prices(p) == {"KX-A": 60, "KX-B": 40}


def test_save_merges_existing(tmp_path):
    p = tmp_path / "state.json"
    save_prior_prices({"KX-A": 60}, p)
    save_prior_prices({"KX-B": 30}, p)
    out = load_prior_prices(p)
    assert out == {"KX-A": 60, "KX-B": 30}


def test_save_overwrites_existing_ticker(tmp_path):
    p = tmp_path / "state.json"
    save_prior_prices({"KX-A": 60}, p)
    save_prior_prices({"KX-A": 75}, p)
    assert load_prior_prices(p) == {"KX-A": 75}


def test_save_evicts_beyond_max_entries(tmp_path):
    p = tmp_path / "state.json"
    save_prior_prices({f"KX-{i:03d}": i for i in range(10)}, p, max_entries=5)
    out = load_prior_prices(p)
    assert len(out) == 5


def test_load_skips_non_numeric(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"tickers": {
        "KX-OK": {"yes_ask": 50, "updated": "now"},
        "KX-BAD": {"yes_ask": "garbage", "updated": "now"},
    }}))
    assert load_prior_prices(p) == {"KX-OK": 50}
