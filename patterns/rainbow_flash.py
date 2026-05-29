import time
import random
from patterns.base import Pattern
from color import hsv_to_rgb


class RainbowFlashPattern(Pattern):
    """Holds a random saturated color for a fixed duration then picks a new one."""

    def __init__(self, hold_ms=300):
        self._hold_ms = hold_ms

    def reset(self, now_ms):
        self._color = hsv_to_rgb(random.randint(0, 255), 255, 255)
        self._next = now_ms + self._hold_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._next) >= 0:
            self._color = hsv_to_rgb(random.randint(0, 255), 255, 255)
            self._next = now_ms + self._hold_ms
            strip.fill(self._color)
