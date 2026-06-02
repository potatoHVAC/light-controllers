class Fixture:
    """Owns one or more Strip instances and drives them through named scenes.

    A scene is any Scene instance (ComposedScene, UniformScene, or custom).
    The fixture is always responsible for calling show() — patterns never
    flush to hardware directly.

    Usage:
        fixture = Fixture([primary, secondary])
        fixture.add_scene("breathe", UniformScene(BreathePattern(RED)))
        fixture.add_scene("dna", ComposedScene(DNASweepPattern(RED), SpinnerPattern(RED)))
        fixture.play("dna", now_ms)
    """

    def __init__(self, strips):
        """strips: list of Strip instances in render order (index 0 = primary)."""
        self._strips = strips
        self._scenes = {}
        self._current = None

    @property
    def strips(self):
        return self._strips

    def add_scene(self, name, scene):
        """Register a named scene."""
        self._scenes[name] = scene

    def play(self, name, now_ms):
        """Switch to a named scene and reset its state."""
        if name not in self._scenes:
            try:
                import log
                log.write('fixture', 'unknown scene: ' + str(name), level='warn')
            except Exception:
                pass
            return
        self._current = self._scenes[name]
        self._current.reset(now_ms)

    def update(self, now_ms):
        """Advance the current scene one tick and flush all strips to hardware."""
        if self._current is None:
            return
        self._current.update(self._strips, now_ms)
        for strip in self._strips:
            strip.show()

    def set_dim(self, factor):
        """Set brightness ceiling on all strips. 1.0 = full, 0.0 = off."""
        for strip in self._strips:
            strip.dim = factor

    def clear(self):
        """Turn off all strips immediately."""
        for strip in self._strips:
            strip.clear()
