from types import SimpleNamespace
from unittest.mock import MagicMock

from analyzer import Analyzer


def _market():
    return {
        "ticker": "KX-FOO-26", "title": "Will X happen?", "subtitle": "",
        "yes_bid": 50, "yes_ask": 60, "no_bid": 40, "no_ask": 50,
        "last_price": 55, "volume_24h": 5000,
        "open_interest": 200, "liquidity": 800,
        "event_ticker": "KX-FOO", "category": "Politics",
        "close_time": "2026-12-31T23:59Z",
        "rules_primary": "Resolves YES if X.",
    }


def _tool_use_block(name, input_dict):
    return SimpleNamespace(type="tool_use", name=name, input=input_dict)


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _usage_obj():
    return SimpleNamespace(
        input_tokens=1000, output_tokens=200,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=1),
        model_dump=lambda: {
            "input_tokens": 1000, "output_tokens": 200,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            "server_tool_use": {"web_search_requests": 1},
        },
    )


def _mock_response(content):
    return SimpleNamespace(content=content, usage=_usage_obj())


def _make_analyzer():
    a = Analyzer.__new__(Analyzer)  # bypass __init__ (which constructs Anthropic())
    a.client = MagicMock()
    a.model = "claude-sonnet-4-6"
    a.max_searches = 5
    a.max_tokens = 2048
    return a


def test_analyzer_extracts_submit_recommendation():
    a = _make_analyzer()
    submit_input = {
        "my_estimate_pct": 72, "market_implied_pct": 60, "edge_pp": 12,
        "recommendation": "BUY_YES", "confidence": "MEDIUM",
        "reasoning": "Polls suggest...", "key_sources": ["https://example.com"],
    }
    a.client.messages.create.return_value = _mock_response([
        _text_block("Searching..."),
        _tool_use_block("submit_recommendation", submit_input),
    ])
    out = a.analyze(_market())
    assert out["recommendation"] == "BUY_YES"
    assert out["edge_pp"] == 12
    assert out["_usage"]["input_tokens"] == 1000


def test_analyzer_retries_then_falls_back():
    a = _make_analyzer()
    a.client.messages.create.return_value = _mock_response([
        _text_block("Researched but forgot to call the tool")
    ])
    out = a.analyze(_market())
    assert out["recommendation"] == "PASS"
    assert out["confidence"] == "LOW"
    assert "Model failed" in out["reasoning"]
    assert a.client.messages.create.call_count == 2


def test_analyzer_succeeds_on_retry():
    a = _make_analyzer()
    submit_input = {
        "my_estimate_pct": 50, "market_implied_pct": 50, "edge_pp": 0,
        "recommendation": "PASS", "confidence": "LOW",
        "reasoning": "thin evidence", "key_sources": [],
    }
    bad = _mock_response([_text_block("oops no tool call")])
    good = _mock_response([_tool_use_block("submit_recommendation", submit_input)])
    a.client.messages.create.side_effect = [bad, good]
    out = a.analyze(_market())
    assert out["recommendation"] == "PASS"
    assert out["confidence"] == "LOW"
    assert "thin evidence" in out["reasoning"]
    assert a.client.messages.create.call_count == 2


def test_analyzer_ignores_other_tool_use_blocks():
    a = _make_analyzer()
    submit_input = {
        "my_estimate_pct": 30, "market_implied_pct": 50, "edge_pp": -20,
        "recommendation": "BUY_NO", "confidence": "HIGH",
        "reasoning": "no", "key_sources": [],
    }
    a.client.messages.create.return_value = _mock_response([
        _tool_use_block("web_search", {"query": "foo"}),
        _text_block("Found stuff"),
        _tool_use_block("submit_recommendation", submit_input),
    ])
    out = a.analyze(_market())
    assert out["recommendation"] == "BUY_NO"
    assert out["edge_pp"] == -20
