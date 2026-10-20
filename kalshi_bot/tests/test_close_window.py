from datetime import datetime, timedelta, timezone

from kalshi_client import close_within_days


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_close_within_days_none_means_no_filter():
    assert close_within_days({"close_time": "2026-01-01T00:00:00Z"}, None) is True
    assert close_within_days({}, None) is True


def test_close_within_days_recent_future_passes():
    future = datetime.now(timezone.utc) + timedelta(days=3)
    assert close_within_days({"close_time": _iso(future)}, max_days=10) is True


def test_close_within_days_far_future_fails():
    future = datetime.now(timezone.utc) + timedelta(days=30)
    assert close_within_days({"close_time": _iso(future)}, max_days=10) is False


def test_close_within_days_already_past_fails():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert close_within_days({"close_time": _iso(past)}, max_days=10) is False


def test_close_within_days_at_edge_passes():
    future = datetime.now(timezone.utc) + timedelta(days=9, hours=23)
    assert close_within_days({"close_time": _iso(future)}, max_days=10) is True


def test_close_within_days_missing_close_time_fails():
    assert close_within_days({}, max_days=10) is False


def test_close_within_days_malformed_time_fails():
    assert close_within_days({"close_time": "garbage"}, max_days=10) is False
    assert close_within_days({"close_time": None}, max_days=10) is False


def test_close_within_days_handles_offset_format():
    future = datetime.now(timezone.utc) + timedelta(days=3)
    iso_with_offset = future.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    assert close_within_days({"close_time": iso_with_offset}, max_days=10) is True
