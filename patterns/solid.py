from patterns.base import Pattern


class SolidPattern(Pattern):
    """Fills the strip with a single solid color."""

    def __init__(self, color):
        self._color = color

    def update(self, strip, now_ms):
        strip.fill(self._color)
