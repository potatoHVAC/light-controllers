import time
from patterns.base import Pattern
from color import scale


class BreatheFromCenterPattern(Pattern):
    """Light expands outward from the strip midpoint in sync with a breathe envelope."""

    def __init__(self, color, half_ms=1200):
        self._color = color
        self._half_ms = half_ms

    def reset(self, now_ms):
        self._start = now_ms

    def update(self, strip, now_ms):
        elapsed = time.ticks_diff(now_ms, self._start) % (self._half_ms * 2)
        t = (elapsed / self._half_ms) if elapsed < self._half_ms else (1.0 - (elapsed - self._half_ms) / self._half_ms)
        envelope = t * t * (3.0 - 2.0 * t)
        center = strip.num_leds // 2
        for i in range(strip.num_leds):
            dist = abs(i - center)
            brightness = envelope * (1.0 - dist / center) if dist <= envelope * center else 0.0
            strip[i] = scale(self._color, brightness)
