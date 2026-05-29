import time
from patterns.base import Pattern
from color import scale, exp_falloff
from strip import BLACK


class SpinnerPattern(Pattern):
    """A comet arc orbits the strip as a ring."""

    def __init__(self, color, arc_len=5, speed_ms=40):
        self._color = color
        self._arc_len = arc_len
        self._speed_ms = speed_ms

    def reset(self, now_ms):
        self._pos = 0
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._speed_ms:
            return
        self._last_update = now_ms
        strip.fill(BLACK)
        for i in range(self._arc_len):
            idx = (self._pos - i) % strip.num_leds
            strip[idx] = scale(self._color, exp_falloff(i))
        self._pos = (self._pos + 1) % strip.num_leds
