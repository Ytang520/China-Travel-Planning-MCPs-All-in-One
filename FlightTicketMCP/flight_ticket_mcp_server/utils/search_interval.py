"""Serialize flight page searches and leave a gap after each completed attempt."""

from contextlib import contextmanager
import logging
import math
import os
import random
import threading
import time

logger = logging.getLogger(__name__)


def _delay(name, default):
    try:
        value = float(os.environ.get(name, default))
        return value if math.isfinite(value) and value >= 0 else default
    except (ValueError, TypeError):
        return default


class FlightSearchInterval:
    """Shared by all searchers in one provider process, including fallback attempts."""

    def __init__(self, *, clock=None, sleep=None, uniform=None):
        self._clock = clock or time.monotonic
        self._sleep = sleep
        self._uniform = uniform or random.uniform
        self._lock = threading.Lock()
        self._finished_at = None

    @contextmanager
    def search(self):
        with self._lock:
            minimum = _delay("FLIGHT_MCP_MIN_DELAY", 15.0)
            maximum = max(minimum, _delay("FLIGHT_MCP_MAX_DELAY", 45.0))
            waited = 0.0
            if self._finished_at is not None:
                delay = self._uniform(minimum, maximum)
                waited = max(0.0, delay - (self._clock() - self._finished_at))
                if waited:
                    logger.info("航班搜索间隔等待 %.1f 秒", waited)
                    (self._sleep or time.sleep)(waited)
            try:
                yield {"waited_seconds": round(waited, 3)}
            finally:
                self._finished_at = self._clock()
