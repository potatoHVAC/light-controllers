import math


class Pattern:
    def start(self):
        pass

    def duty(self, elapsed_ms):
        raise NotImplementedError


class OnPattern(Pattern):
    def duty(self, elapsed_ms):
        return 1023


class OffPattern(Pattern):
    def duty(self, elapsed_ms):
        return 0


class PulsePattern(Pattern):
    def __init__(self, period_ms=2000):
        self.period_ms = period_ms

    def duty(self, elapsed_ms):
        t = (elapsed_ms % self.period_ms) / self.period_ms
        brightness = (math.sin(t * 2 * math.pi - math.pi / 2) + 1) / 2
        return int(brightness * 1023)


class StrobePattern(Pattern):
    def __init__(self, rate_ms=100):
        self.rate_ms = rate_ms

    def duty(self, elapsed_ms):
        return 1023 if (elapsed_ms // self.rate_ms) % 2 == 0 else 0


PATTERNS = [
    OnPattern(),
    PulsePattern(period_ms=2000),
    StrobePattern(rate_ms=100),
    OffPattern(),
]
