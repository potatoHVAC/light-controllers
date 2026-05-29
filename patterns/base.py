class Pattern:
    """Operates on a single strip. Never calls show()."""

    def reset(self, now_ms):
        """Called when switching to this pattern. Reset all internal state."""
        pass

    def update(self, strip, now_ms):
        """Advance one tick and write pixel values to the strip. Never call show()."""
        raise NotImplementedError


class Scene:
    """Coordinates one or more patterns across a fixture's strips.
    Receives the full strip list; dispatches to individual Pattern instances."""

    def reset(self, now_ms):
        pass

    def update(self, strips, now_ms):
        raise NotImplementedError


class ComposedScene(Scene):
    """Assigns one Pattern per strip. Patterns run independently with no
    shared state — coordination is the theme's responsibility, not the pattern's.

    Usage:
        ComposedScene(BreathePattern(RED), SpinnerPattern(RED))
        # strips[0] → BreathePattern, strips[1] → SpinnerPattern
    """

    def __init__(self, *patterns):
        self._patterns = patterns

    def reset(self, now_ms):
        for p in self._patterns:
            p.reset(now_ms)

    def update(self, strips, now_ms):
        for strip, pattern in zip(strips, self._patterns):
            pattern.update(strip, now_ms)


class UniformScene(Scene):
    """Applies a single Pattern to every strip in the fixture."""

    def __init__(self, pattern):
        self._pattern = pattern

    def reset(self, now_ms):
        self._pattern.reset(now_ms)

    def update(self, strips, now_ms):
        for strip in strips:
            self._pattern.update(strip, now_ms)
