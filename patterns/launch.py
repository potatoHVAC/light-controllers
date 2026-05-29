import time
from patterns.base import Pattern
from color import scale
from strip import BLACK, PULSE_LEN


class _Pulse:
    def __init__(self, now_ms):
        self.pos = 0
        self.active = True
        self.last_step = now_ms


class LaunchPattern(Pattern):
    """Pulses launch from index 0 toward the end of the strip and repeat."""

    def __init__(self, color, max_pulses=4, step_ms=50, delay_ms=1300):
        """max_pulses: simultaneous pulses in flight.
        delay_ms: gap between pulse spawns."""
        self._color = color
        self._max_pulses = max_pulses
        self._step_ms = step_ms
        self._delay_ms = delay_ms

    def reset(self, now_ms):
        self._pulses = [None] * self._max_pulses
        self._pulses[0] = _Pulse(now_ms)
        self._last_spawn = now_ms

    def update(self, strip, now_ms):
        strip.fill(BLACK)
        for p in self._pulses:
            if p is None or not p.active:
                continue
            if time.ticks_diff(now_ms, p.last_step) >= self._step_ms:
                p.last_step = now_ms
                p.pos += 1
                if p.pos >= strip.num_leds + PULSE_LEN:
                    p.active = False
            strip.draw_pulse(p.pos, 1, self._color)

        if time.ticks_diff(now_ms, self._last_spawn) >= self._delay_ms:
            self._last_spawn = now_ms + 99999
            for i in range(self._max_pulses):
                if self._pulses[i] is None or not self._pulses[i].active:
                    self._pulses[i] = _Pulse(now_ms)
                    break
