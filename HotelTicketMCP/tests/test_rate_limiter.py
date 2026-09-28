import random

import pytest

from hotel_ticket_mcp_server.utils.rate_limiter import SearchRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeSleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)
        clock.now += seconds


clock = FakeClock()
sleep = FakeSleep()


def make_limiter(min_delay=30.0, max_delay=300.0, seed=0):
    return SearchRateLimiter(
        min_delay=min_delay,
        max_delay=max_delay,
        clock=clock,
        sleep=sleep,
        rng=random.Random(seed),
    )


@pytest.fixture(autouse=True)
def reset():
    clock.now = 1000.0
    sleep.calls.clear()
    yield


def test_first_search_does_not_wait():
    limiter = make_limiter()
    result = limiter.wait_if_needed()
    assert result["reason"] == "first_search"
    assert result["waited_seconds"] == 0.0
    assert sleep.calls == []


def test_second_search_waits_random_delay():
    limiter = make_limiter(seed=0)
    limiter.wait_if_needed()
    clock.now += 5  # 5s since first search
    result = limiter.wait_if_needed()
    expected = random.Random(0).uniform(30.0, 300.0)
    assert result["reason"] == "rate_limit"
    assert result["delay_seconds"] == pytest.approx(expected)
    assert result["waited_seconds"] == pytest.approx(max(0.0, expected - 5))
    if result["waited_seconds"] > 0:
        assert sleep.calls == [result["waited_seconds"]]
    else:
        assert sleep.calls == []


def test_no_wait_when_delay_already_elapsed():
    limiter = make_limiter(seed=1)
    limiter.wait_if_needed()
    clock.now += 10000  # far beyond any possible delay
    result = limiter.wait_if_needed()
    assert result["waited_seconds"] == 0.0
    assert sleep.calls == []


def test_invalid_range_raises():
    with pytest.raises(ValueError):
        SearchRateLimiter(min_delay=300.0, max_delay=30.0, clock=clock, sleep=sleep)
    with pytest.raises(ValueError):
        SearchRateLimiter(min_delay=-1.0, max_delay=300.0, clock=clock, sleep=sleep)
