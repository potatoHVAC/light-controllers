import time
import storage


class Controller:
    """Manages themes and scenes for a fixture.

    Short press cycles scenes within the current theme.
    Long press advances to the next theme and resets to scene 0.
    State is saved to flash 2 seconds after the last button event.
    """

    SAVE_DELAY_MS = 2000

    def __init__(self, fixture, themes, network=None):
        self._fixture = fixture
        self._themes = themes
        self._network = network
        self._save_pending = False
        self._save_after = 0
        self._scenes = []

        state = storage.load({'theme': 0, 'scenes': [0] * len(themes)})
        self._theme_idx = min(state['theme'], len(themes) - 1)
        self._scene_idxs = state['scenes']
        if len(self._scene_idxs) < len(themes):
            self._scene_idxs += [0] * (len(themes) - len(self._scene_idxs))
        self._load_scenes()
        self._scene_idxs[self._theme_idx] = min(
            self._scene_idxs[self._theme_idx], len(self._scenes) - 1
        )

    def start(self, now_ms):
        """Play the initial scene. Call once after construction."""
        self._play_current(now_ms)

    def next_scene(self, now_ms):
        self._scene_idxs[self._theme_idx] = (self._scene_idxs[self._theme_idx] + 1) % len(self._scenes)
        self._play_current(now_ms)
        self._schedule_save(now_ms)
        if self._network:
            self._network.broadcast_pattern(self._scene_idxs[self._theme_idx])

    def next_theme(self, now_ms):
        self._theme_idx = (self._theme_idx + 1) % len(self._themes)
        self._load_scenes()
        self._play_current(now_ms)
        self._schedule_save(now_ms)
        if self._network:
            self._network.broadcast_pattern(self._scene_idxs[self._theme_idx])

    def update(self, now_ms):
        """Advance the current scene and flush to hardware. Call every loop tick."""
        self._fixture.update(now_ms)
        if self._save_pending and time.ticks_diff(now_ms, self._save_after) >= 0:
            self._save_pending = False
            storage.save({'theme': self._theme_idx, 'scenes': self._scene_idxs})

    def _load_scenes(self):
        self._scenes = self._themes[self._theme_idx].scenes()
        for name, scene in self._scenes:
            self._fixture.add_scene(name, scene)

    def _play_current(self, now_ms):
        name, _ = self._scenes[self._scene_idxs[self._theme_idx]]
        self._fixture.play(name, now_ms)

    def _schedule_save(self, now_ms):
        self._save_pending = True
        self._save_after = time.ticks_add(now_ms, self.SAVE_DELAY_MS)
