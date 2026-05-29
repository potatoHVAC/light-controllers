import random
import time
from patterns.base import Pattern
from color import hsv_to_rgb
from strip import BLACK


class GlitterPattern(Pattern):
    """Random sparse sparkles at random hues on a black background."""

    def __init__(self, update_ms=25, chance=15):
        """chance: probability of each LED sparkling per update (0-255)."""
        self._update_ms = update_ms
        self._chance = chance

    def reset(self, now_ms):
        self._last_update = now_ms

    def update(self, strip, now_ms):
        if time.ticks_diff(now_ms, self._last_update) < self._update_ms:
            return
        self._last_update = now_ms
        strip.fill(BLACK)
        for i in range(strip.num_leds):
            if random.randint(0, 255) < self._chance:
                strip[i] = hsv_to_rgb(random.randint(0, 255), 255, 255)
