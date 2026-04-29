import time
from machine import Pin, PWM
from patterns import PATTERNS


class LightRig:
    def __init__(self, gpio=16):
        self.pwm = PWM(Pin(gpio), freq=1000)
        self.pattern_index = 0
        self._start_ms = time.ticks_ms()
        PATTERNS[self.pattern_index].start()

    def next_pattern(self):
        self.pattern_index = (self.pattern_index + 1) % len(PATTERNS)
        self._reset_pattern()

    def set_pattern(self, index):
        index = index % len(PATTERNS)
        if index != self.pattern_index:
            self.pattern_index = index
            self._reset_pattern()

    def update(self, now_ms):
        elapsed = time.ticks_diff(now_ms, self._start_ms)
        self.pwm.duty(PATTERNS[self.pattern_index].duty(elapsed))

    def _reset_pattern(self):
        self._start_ms = time.ticks_ms()
        PATTERNS[self.pattern_index].start()
