import math
import time
from patterns.base import Pattern
from color import scale


class ResonancePattern(Pattern):
    """A standing wave with slowly modulating frequency."""

    def __init__(self, color, update_ms=20, phase_step=0.05, freq_step=0.003,
                 freq_base=1.5, freq_range=0.7):
        self._color = color
        self._update_ms = update_ms
        self._phase_step = phase_step
        self._freq_step = freq_step
        self._freq_base = freq_base
        self._freq_range = freq_range

    def reset(self, now_ms):
        self._phase = 0.0
        self._freq_phase = 0.0
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._update_ms:
            return
        self._last_update = now_ms
        self._phase += self._phase_step
        self._freq_phase += self._freq_step
        freq = self._freq_base + self._freq_range * math.sin(self._freq_phase)
        for i in range(strip.num_leds):
            pos = i / (strip.num_leds - 1)
            wave = 0.5 + 0.5 * math.sin(self._phase + pos * freq * 2.0 * math.pi)
            strip[i] = scale(self._color, wave * wave)
