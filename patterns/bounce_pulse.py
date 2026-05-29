import time
from patterns.base import Pattern
from strip import BLACK


class BouncePulsePattern(Pattern):
    """A comet pulse bounces end to end on a single strip."""

    def __init__(self, color, pulse_speed_ms=40):
        self._color = color
        self._pulse_speed_ms = pulse_speed_ms

    def reset(self, now_ms):
        self._pos = 0
        self._dir = 1
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._pulse_speed_ms:
            return
        self._last_update = now_ms
        strip.fill(BLACK)
        strip.draw_pulse(self._pos, self._dir, self._color)
        self._pos += self._dir
        if self._pos >= strip.num_leds:
            self._pos = strip.num_leds - 1
            self._dir = -1
        elif self._pos < 0:
            self._pos = 0
            self._dir = 1
