class Pattern:
    def start(self):
        pass

    def duty(self, elapsed_ms):
        raise NotImplementedError


class OnPattern(Pattern):
    def duty(self, elapsed_ms):
        return 1023


class HalfPattern(Pattern):
    def duty(self, elapsed_ms):
        return 511


class OffPattern(Pattern):
    def duty(self, elapsed_ms):
        return 0


class StrobePattern(Pattern):
    def __init__(self, rate_ms=500):
        self.rate_ms = rate_ms

    def duty(self, elapsed_ms):
        return 1023 if (elapsed_ms // self.rate_ms) % 2 == 0 else 0


PATTERNS = [
    OnPattern(),
    HalfPattern(),
    OffPattern(),
    StrobePattern(rate_ms=500),
]
