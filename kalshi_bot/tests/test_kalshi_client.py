import pytest

from kalshi_client import KalshiClient, _clean_market, summarize_orderbook


def _market(**overrides):
    base = {
        "ticker": "KX-FOO-26",
        "title": "Will X happen?",
        "subtitle": "subtitle",
        "status": "open",
        "yes_bid": 50, "yes_ask": 52, "no_bid": 48, "no_ask": 50,
        "last_price": 51, "previous_price": 50, "previous_yes_ask": 51,
        "volume": 1000, "volume_24h": 5000,
        "open_interest": 200, "liquidity": 800,
        "close_time": "2026-12-31T23:59Z",
    }
    base.update(overrides)
    return base


def test_clean_market_keeps_valid():
    out = _clean_market(_market())
    assert out is not None
    assert out["yes_ask"] == 52
    assert out["volume_24h"] == 5000


def test_clean_market_rejects_missing_yes_ask():
    assert _clean_market(_market(yes_ask=None)) is None


def test_clean_market_rejects_blank_title():
    assert _clean_market(_market(title="")) is None


def test_clean_market_rejects_missing_status():
    m = _market()
    del m["status"]
    assert _clean_market(m) is None


def test_clean_market_coerces_none_volume():
    out = _clean_market(_market(volume_24h=None))
    assert out["volume_24h"] == 0


def test_clean_market_coerces_garbage_volume():
    out = _clean_market(_market(volume_24h="garbage"))
    assert out["volume_24h"] == 0


def test_summarize_orderbook_empty():
    assert summarize_orderbook({"yes": [], "no": []}) == "YES top: (empty) | NO top: (empty)"


def test_summarize_orderbook_missing_keys():
    s = summarize_orderbook({})
    assert "YES top:" in s and "NO top:" in s


def test_summarize_orderbook_garbage_yes():
    s = summarize_orderbook({"yes": "garbage", "no": None})
    assert "YES top: (empty)" in s


def test_summarize_orderbook_not_dict():
    assert summarize_orderbook(None) == "(unavailable)"
    assert summarize_orderbook("garbage") == "(unavailable)"


def test_summarize_orderbook_normal():
    s = summarize_orderbook({"yes": [[55, 100], [54, 200]], "no": [[44, 50]]})
    assert "55¢×100" in s
    assert "44¢×50" in s


def test_select_markets_volume(monkeypatch):
    client = KalshiClient()
    markets = [
        _market(ticker="KX-A", volume_24h=10_000),
        _market(ticker="KX-B", volume_24h=500),
        _market(ticker="KX-C", volume_24h=5_000),
    ]
    monkeypatch.setattr(client, "iter_markets", lambda **kw: iter(markets))
    out = client.select_markets("volume", n=10, min_volume=1000)
    assert [m["ticker"] for m in out] == ["KX-A", "KX-C"]


def test_select_markets_illiquid(monkeypatch):
    client = KalshiClient()
    markets = [
        _market(ticker="KX-TIGHT", yes_bid=50, yes_ask=52, volume_24h=5000),
        _market(ticker="KX-WIDE", yes_bid=40, yes_ask=50, volume_24h=2000),
        _market(ticker="KX-MEDIUM", yes_bid=45, yes_ask=51, volume_24h=2000),
    ]
    monkeypatch.setattr(client, "iter_markets", lambda **kw: iter(markets))
    out = client.select_markets("illiquid", n=10, min_volume=1000)
    assert [m["ticker"] for m in out] == ["KX-WIDE", "KX-MEDIUM"]


def test_select_markets_movers(monkeypatch):
    client = KalshiClient()
    markets = [
        _market(ticker="KX-BIG", yes_ask=70, volume_24h=5000),
        _market(ticker="KX-SMALL", yes_ask=51, volume_24h=5000),
        _market(ticker="KX-NONE", yes_ask=50, volume_24h=5000),
    ]
    monkeypatch.setattr(client, "iter_markets", lambda **kw: iter(markets))
    prior = {"KX-BIG": 50, "KX-SMALL": 50, "KX-NONE": 50}
    out = client.select_markets("movers", n=10, min_volume=1000, prior_prices=prior)
    assert out[0]["ticker"] == "KX-BIG"
    assert all(m["ticker"] != "KX-NONE" for m in out)


def test_select_markets_unknown_mode():
    client = KalshiClient()
    with pytest.raises(ValueError):
        client.select_markets("nonsense", n=5, min_volume=0)


def test_iter_markets_drops_invalid(monkeypatch):
    client = KalshiClient()
    pages = [{
        "markets": [
            _market(ticker="KX-OK", volume_24h=5000),
            _market(ticker="KX-BAD", yes_ask=None),
            _market(ticker="KX-OK2", volume_24h=2000),
        ],
        "cursor": None,
    }]
    monkeypatch.setattr(client, "_get", lambda *a, **kw: pages.pop(0))
    out = list(client.iter_markets())
    assert [m["ticker"] for m in out] == ["KX-OK", "KX-OK2"]
    assert client.dropped_markets == 1
