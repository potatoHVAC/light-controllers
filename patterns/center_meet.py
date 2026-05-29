import time
from patterns.base import Pattern
from strip import BLACK


class CenterMeetPattern(Pattern):
    """Two pulses start at opposite ends of the strip, travel inward to the
    center, then reflect back outward. The right pulse is always derived from
    the left position so they can never drift out of sync."""

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
        right = strip.num_leds - 1 - self._pos
        strip.draw_pulse(self._pos, self._dir,  self._color)
        strip.draw_pulse(right,    -self._dir, self._color)
        self._pos += self._dir
        mid = strip.num_leds // 2
        if self._pos >= mid:
            self._pos = mid
            self._dir = -1
        elif self._pos <= 0:
            self._pos = 0
            self._dir = 1
