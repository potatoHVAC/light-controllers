from patterns import (
    ComposedScene, UniformScene,
    RainbowPattern, FlashRBPattern, RainbowFlashPattern, FireflyPattern, GlitterPattern,
    SolidPattern, BouncePulsePattern, CenterMeetPattern, BreathePattern,
    SpinnerPattern, DNASweepPattern, BreatheFromCenterPattern, LaunchPattern, ResonancePattern,
)
from color import scale

RED  = (255, 0, 0)
BLUE = (0, 0, 255)


class Theme:
    """Base class for all themes. A theme is a named, ordered list of scenes
    that a fixture can cycle through."""

    def scenes(self):
        """Return a list of (name, scene) tuples in display order."""
        raise NotImplementedError


class ColorTheme(Theme):
    """Single-color theme. Pass any RGB tuple to select the color.

    Full scene list is defined here — active scenes are controlled by
    which patterns are included in scenes(). Expand as needed.

    Usage:
        ColorTheme((255, 0, 0))   # red
        ColorTheme((0, 0, 255))   # blue
    """

    def __init__(self, color):
        self._color = color

    def scenes(self):
        return [
            ("solid",   UniformScene(SolidPattern(self._color))),
            ("breathe", UniformScene(BreathePattern(self._color))),
        ]


class RandomTheme(Theme):
    """Multi-color patterns. Each strip gets an independent pattern instance
    so strips animate independently."""

    def scenes(self):
        return [
            ("rainbow", ComposedScene(RainbowPattern(hue_start=0), RainbowPattern(hue_start=64))),
            ("firefly", ComposedScene(FireflyPattern(), FireflyPattern())),
        ]
