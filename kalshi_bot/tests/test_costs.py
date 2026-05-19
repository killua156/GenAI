from costs import estimate, from_usage


def test_estimate_linear():
    s1 = estimate(1, "claude-sonnet-4-6", 5)
    s10 = estimate(10, "claude-sonnet-4-6", 5)
    assert abs(s10 - 10 * s1) < 0.01


def test_estimate_higher_for_opus():
    # Opus tokens are 5x Sonnet, but per-search cost is flat, so total ratio is ~2x at 5 searches.
    s = estimate(1, "claude-sonnet-4-6", 5)
    o = estimate(1, "claude-opus-4-7", 5)
    assert o > s * 2


def test_estimate_lower_for_haiku():
    s = estimate(1, "claude-sonnet-4-6", 5)
    h = estimate(1, "claude-haiku-4-5-20251001", 5)
    assert h < s


def test_estimate_unknown_model_falls_back():
    known = estimate(1, "claude-sonnet-4-6", 5)
    unknown = estimate(1, "not-a-model", 5)
    assert known == unknown


def test_estimate_zero_searches():
    s_no = estimate(1, "claude-sonnet-4-6", 0)
    s_yes = estimate(1, "claude-sonnet-4-6", 5)
    assert s_yes > s_no


def test_from_usage_basic():
    usage = {
        "input_tokens": 4000, "output_tokens": 500,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        "server_tool_use": {"web_search_requests": 5},
    }
    cost = from_usage(usage, "claude-sonnet-4-6")
    # 4000*3/1M = 0.012; 500*15/1M = 0.0075; 5*0.01 = 0.05  => 0.0695
    assert abs(cost - 0.0695) < 0.001


def test_from_usage_cache_savings():
    no_cache = from_usage(
        {"input_tokens": 4000, "output_tokens": 0,
         "server_tool_use": {"web_search_requests": 0}},
        "claude-sonnet-4-6",
    )
    cached = from_usage(
        {"input_tokens": 0, "output_tokens": 0,
         "cache_read_input_tokens": 4000,
         "server_tool_use": {"web_search_requests": 0}},
        "claude-sonnet-4-6",
    )
    assert cached < no_cache


def test_from_usage_empty():
    assert from_usage({}, "claude-sonnet-4-6") == 0.0
    assert from_usage(None, "claude-sonnet-4-6") == 0.0
