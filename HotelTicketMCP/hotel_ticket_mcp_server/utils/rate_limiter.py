"""搜索间隔限速：两次搜索之间等待随机 30~300 秒（首次不等待）。

防封设计：酒店搜索需要登录态，频繁搜索有账号封禁风险，
因此每次搜索前等待一个随机间隔（默认 30s~5min，可用环境变量调整）。
"""

import logging
import os
import random
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_MIN_DELAY = 30.0
DEFAULT_MAX_DELAY = 300.0


def _env_float(name, default):
    """读取延迟环境变量：空值/非法值静默回退默认值（避免子进程因配置笔误而崩溃）。"""
    try:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


class SearchRateLimiter:
    def __init__(
        self,
        min_delay=None,
        max_delay=None,
        clock=time.monotonic,
        sleep=time.sleep,
        rng=None,
    ):
        from_env = min_delay is None or max_delay is None
        self.min_delay = float(
            min_delay
            if min_delay is not None
            else _env_float("HOTEL_MCP_MIN_DELAY", DEFAULT_MIN_DELAY)
        )
        self.max_delay = float(
            max_delay
            if max_delay is not None
            else _env_float("HOTEL_MCP_MAX_DELAY", DEFAULT_MAX_DELAY)
        )
        if from_env:
            # 环境变量来源的配置做钳制（配置笔误不应让子进程在 import 时崩溃），
            # 显式构造参数仍严格校验（依赖该行为的测试与调用方）
            original = (self.min_delay, self.max_delay)
            self.min_delay = max(0.0, self.min_delay)
            self.max_delay = max(self.max_delay, self.min_delay)
            if (self.min_delay, self.max_delay) != original:
                logger.warning(
                    "延迟配置已钳制: (%s, %s) -> (%.0f, %.0f)，"
                    "请检查 HOTEL_MCP_MIN_DELAY/HOTEL_MCP_MAX_DELAY（默认 30~300）",
                    original[0], original[1], self.min_delay, self.max_delay,
                )
        elif self.min_delay < 0 or self.max_delay < self.min_delay:
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
