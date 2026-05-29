import time
from patterns.base import Pattern
from color import scale


class BreathePattern(Pattern):
    """Smooth brightness cycle using a smoothstep envelope."""

    def __init__(self, color, half_ms=1000):
        """half_ms: duration of one half-cycle (fade in or fade out)."""
        self._color = color
        self._half_ms = half_ms

    def reset(self, now_ms):
        self._start = now_ms

    def update(self, strip, now_ms):
        elapsed = time.ticks_diff(now_ms, self._start) % (self._half_ms * 2)
        t = (1.0 - elapsed / self._half_ms) if elapsed < self._half_ms else ((elapsed - self._half_ms) / self._half_ms)
        strip.fill(scale(self._color, t * t * (3.0 - 2.0 * t)))
