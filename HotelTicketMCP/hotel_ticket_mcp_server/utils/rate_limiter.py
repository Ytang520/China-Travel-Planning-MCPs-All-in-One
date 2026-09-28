"""搜索间隔限速：两次搜索之间等待随机 30~300 秒（首次不等待）。

防封设计：酒店搜索需要登录态，频繁搜索有账号封禁风险，
因此每次搜索前等待一个随机间隔（默认 30s~5min，可用环境变量调整）。
"""

import os
import random
import threading
import time

DEFAULT_MIN_DELAY = 30.0
DEFAULT_MAX_DELAY = 300.0


class SearchRateLimiter:
    def __init__(
        self,
        min_delay=None,
        max_delay=None,
        clock=time.monotonic,
        sleep=time.sleep,
        rng=None,
    ):
        self.min_delay = float(
            min_delay
            if min_delay is not None
            else os.environ.get("HOTEL_MCP_MIN_DELAY", DEFAULT_MIN_DELAY)
        )
        self.max_delay = float(
            max_delay
            if max_delay is not None
            else os.environ.get("HOTEL_MCP_MAX_DELAY", DEFAULT_MAX_DELAY)
        )
        if self.min_delay < 0 or self.max_delay < self.min_delay:
            raise ValueError(
                f"invalid delay range: [{self.min_delay}, {self.max_delay}]"
            )
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._last_search_at = None

    def wait_if_needed(self):
        """在本次搜索前等待随机间隔（首次调用不等待）。

        Returns:
            dict: {"waited_seconds": float, "reason": "first_search"|"rate_limit", "delay_seconds": float}
        """
        with self._lock:
            now = self._clock()
            if self._last_search_at is None:
                self._last_search_at = now
                return {
                    "waited_seconds": 0.0,
                    "reason": "first_search",
                    "delay_seconds": 0.0,
                }
            delay = self._rng.uniform(self.min_delay, self.max_delay)
            remaining = max(0.0, delay - (now - self._last_search_at))
            if remaining > 0:
                self._sleep(remaining)
            self._last_search_at = self._clock()
            return {
                "waited_seconds": remaining,
                "reason": "rate_limit",
                "delay_seconds": delay,
            }
