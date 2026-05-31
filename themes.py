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
    that a fixture can cycle through.

    name: unique string identifier broadcast in mesh packets. Controllers that
    receive an unknown name fall back to a solid scene using representative_color()
    if provided. Names must be stable across firmware versions — changing a name
    is a breaking change for mixed-firmware rigs.
    """

    name = None

    def scenes(self):
        """Return a list of (name, scene) tuples in display order."""
        raise NotImplementedError

    def representative_color(self):
        """Return an RGB tuple that represents this theme's color, or None.
        Included in mesh packets so controllers that don't have this theme
        can fall back to a solid scene in roughly the right color."""
        return None


class ColorTheme(Theme):
    """Single-color theme. Pass any RGB tuple and a unique name.

    Usage:
        ColorTheme((255, 0, 0), 'red')
        ColorTheme((0, 0, 255), 'blue')
    """

    def __init__(self, color, name):
        self._color = color
        self.name = name

    def representative_color(self):
        return self._color

    def scenes(self):
        return [
            ("solid",   UniformScene(SolidPattern(self._color))),
            ("breathe", UniformScene(BreathePattern(self._color))),
        ]


class RandomTheme(Theme):
    """Multi-color patterns. Each strip gets an independent pattern instance
    so strips animate independently."""

    name = 'random'

    def scenes(self):
        return [
            ("rainbow", ComposedScene(RainbowPattern(hue_start=0), RainbowPattern(hue_start=64))),
            ("firefly", ComposedScene(FireflyPattern(), FireflyPattern())),
        ]
