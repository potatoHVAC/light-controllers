import time
from patterns.base import Pattern


class FlashRBPattern(Pattern):
    """Alternates a single strip between two colors on a fixed interval."""

    def __init__(self, color_a, color_b, interval_ms=1000):
        self._a = color_a
        self._b = color_b
        self._interval_ms = interval_ms

    def reset(self, now_ms):
        self._flip = False
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._interval_ms:
            return
        self._last_update = now_ms
        self._flip = not self._flip
        strip.fill(self._a if self._flip else self._b)
