import time
from patterns.base import Pattern
from color import hsv_to_rgb


class RainbowPattern(Pattern):
    """Rolling rainbow along a single strip."""

    def __init__(self, interval_ms=10, hue_start=0):
        """hue_start: initial hue offset (0-255). Set different values per strip
        in a ComposedScene to stagger the rainbow across strips."""
        self._interval_ms = interval_ms
        self._hue_start = hue_start

    def reset(self, now_ms):
        self._hue = self._hue_start
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._interval_ms:
            return
        self._last_update = now_ms
        delta = 256 // strip.num_leds
        for i in range(strip.num_leds):
            strip[i] = hsv_to_rgb((self._hue + i * delta) % 256, 255, 255)
        self._hue = (self._hue + 1) % 256
