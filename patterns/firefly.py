import time
import random
from patterns.base import Pattern
from color import hsv_to_rgb


class _Firefly:
    def __init__(self, now_ms, min_wake_ms, max_wake_ms):
        self.hue = random.randint(0, 255)
        self.brightness = 0.0
        self.rising = False
        self.next_wake = now_ms + random.randint(min_wake_ms, max_wake_ms)


class FireflyPattern(Pattern):
    """Each LED independently fades in and out at a random hue with randomised timing."""

    def __init__(self, update_ms=20, rise_rate=0.08, fall_rate=0.025,
                 min_wake_ms=200, max_wake_ms=3000,
                 min_sleep_ms=500, max_sleep_ms=4000):
        self._update_ms = update_ms
        self._rise_rate = rise_rate
        self._fall_rate = fall_rate
        self._min_wake_ms = min_wake_ms
        self._max_wake_ms = max_wake_ms
        self._min_sleep_ms = min_sleep_ms
        self._max_sleep_ms = max_sleep_ms

    def reset(self, now_ms):
        self._flies = None
        self._last_update = now_ms

    def _init(self, strip, now_ms):
        self._flies = [
            _Firefly(now_ms, self._min_wake_ms, self._max_wake_ms)
            for _ in range(strip.num_leds)
        ]

    def update(self, strip, now_ms):
        if self._flies is None:
            self._init(strip, now_ms)
        if time.ticks_diff(now_ms, self._last_update) < self._update_ms:
            return
        self._last_update = now_ms
        for i, f in enumerate(self._flies):
            if f.brightness <= 0.0 and not f.rising:
                if time.ticks_diff(now_ms, f.next_wake) >= 0:
                    f.hue = random.randint(0, 255)
                    f.rising = True
                    f.brightness = 0.01
            elif f.rising:
                f.brightness = min(1.0, f.brightness + self._rise_rate)
                if f.brightness >= 1.0:
                    f.rising = False
            else:
                f.brightness -= self._fall_rate
                if f.brightness <= 0.0:
                    f.brightness = 0.0
                    f.next_wake = now_ms + random.randint(self._min_sleep_ms, self._max_sleep_ms)
            strip[i] = hsv_to_rgb(f.hue, 255, int(f.brightness * 255))
