import time
from patterns.base import Pattern
from color import scale, exp_falloff
from strip import BLACK


class DNASweepPattern(Pattern):
    """A pulse sweeps linearly from one end to the other and repeats."""

    def __init__(self, color, speed_ms=60):
        self._color = color
        self._speed_ms = speed_ms

    def reset(self, now_ms):
        self._pos = 0
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._speed_ms:
            return
        self._last_update = now_ms
        strip.fill(BLACK)
        for i in range(5):
            idx = self._pos - i
            if 0 <= idx < strip.num_leds:
                strip[idx] = scale(self._color, exp_falloff(i))
        self._pos += 1
        if self._pos >= strip.num_leds + 5:
            self._pos = 0
