from soulseek_charts.api.cache import ResponseCache


def test_second_call_is_served_from_the_cache():
    cache = ResponseCache(time_to_live_seconds=60)
    call_count = 0

    def producer():
        nonlocal call_count
        call_count += 1
        return call_count

    assert cache.get_or_call("chart", producer) == 1
    assert cache.get_or_call("chart", producer) == 1
    assert call_count == 1


def test_entry_is_recomputed_after_expiry(monkeypatch):
    current_time = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: current_time[0])

    cache = ResponseCache(time_to_live_seconds=60)
    call_count = 0

    def producer():
        nonlocal call_count
        call_count += 1
        return call_count

    assert cache.get_or_call("chart", producer) == 1

    current_time[0] += 61
    assert cache.get_or_call("chart", producer) == 2
    assert call_count == 2


def test_distinct_keys_do_not_share_a_value():
    cache = ResponseCache()

    assert cache.get_or_call("artists", lambda: "a") == "a"
    assert cache.get_or_call("tracks", lambda: "t") == "t"
