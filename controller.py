import time
import storage


class Controller:
    """Manages themes and scenes for a fixture.

    Short press cycles scenes within the current theme.
    Long press advances to the next theme and resets to scene 0.
    State is saved to flash after save_delay_ms following the last button event.
    Dim is a network-level ceiling applied to all strips; it is not persisted.

    Solo mode: the soloist stays at full brightness and broadcasts solo_dim to
    all other controllers. Heartbeats carry the dim level followers should use
    (_network_dim), not the sender's own dim, so the soloist's heartbeats don't
    accidentally restore followers to full brightness.
    """

    def __init__(self, fixture, themes, network=None, solo_dim=0.2, save_delay_ms=2000):
        self._fixture = fixture
        self._themes = themes
        self._network = network
        self._solo_dim = solo_dim
        self._save_delay_ms = save_delay_ms
        self._save_pending = False
        self._save_after = 0
        self._scenes = []
        self._dim = 1.0
        self._is_soloist = False
        self._solo_active = False
        self._solo_dim_target = solo_dim

        state = storage.load({'theme': 0, 'scenes': [0] * len(themes)})
        self._theme_idx = min(state['theme'], len(themes) - 1)
        self._scene_idxs = state['scenes']
        if len(self._scene_idxs) < len(themes):
            self._scene_idxs += [0] * (len(themes) - len(self._scene_idxs))
        for i, theme in enumerate(themes):
            limit = len(theme.scenes())
            self._scene_idxs[i] = min(self._scene_idxs[i], limit - 1)
        self._load_scenes()

    def start(self, now_ms, button=None):
        """Wait for network sync then play the initial scene.

        Uses tick() so heartbeat_request messages are properly handled during
        the wait — without this, simultaneous boots deadlock because no
        controller processes requests while everyone is waiting for a heartbeat.

        If button is provided, a press starts immediately from stored state
        rather than waiting indefinitely. Button is locked out once a network
        sync message arrives so a simultaneous press can't override network data.
        """
        if self._network and button:
            synced = False
            while True:
                now_ms = time.ticks_ms()
                msg = self._network.tick(
                    self._theme_idx,
                    self._scene_idxs[self._theme_idx],
                    self._network_dim(),
                    now_ms,
                )
                if msg:
                    msg_type = msg.get('type')
                    if msg_type in ('heartbeat', 'change'):
                        self._apply_network_state(msg.get('theme', 0), msg.get('scene', 0), now_ms)
                        if not self._is_soloist:
                            self.set_dim(msg.get('dim', 1.0))
                        synced = True
                        break
                    elif msg_type in ('solo', 'dim'):
                        self._handle_dim_msg(msg)
                if not synced and button.update(now_ms):
                    break
            self._network.announce()
        self._play_current(now_ms)

    def next_scene(self, now_ms):
        self._scene_idxs[self._theme_idx] = (self._scene_idxs[self._theme_idx] + 1) % len(self._scenes)
        self._play_current(now_ms)
        self._schedule_save(now_ms)
        if self._network:
            self._network.send_change(self._theme_idx, self._scene_idxs[self._theme_idx], self._network_dim())

    def next_theme(self, now_ms):
        self._theme_idx = (self._theme_idx + 1) % len(self._themes)
        self._load_scenes()
        self._play_current(now_ms)
        self._schedule_save(now_ms)
        if self._network:
            self._network.send_change(self._theme_idx, self._scene_idxs[self._theme_idx], self._network_dim())

    def solo(self):
        """Broadcast solo: this controller stays full, all others dim."""
        self._is_soloist = True
        self._solo_active = True
        self._solo_dim_target = self._solo_dim
        self.set_dim(1.0)
        if self._network:
            self._network.send_solo(active=True, dim=self._solo_dim)

    def release_solo(self):
        """Release solo: restore full brightness across the mesh."""
        self._is_soloist = False
        self._solo_active = False
        self.set_dim(1.0)
        if self._network:
            self._network.send_solo(active=False)

    def set_dim(self, factor):
        """Apply a brightness ceiling to all strips."""
        self._dim = max(0.0, min(1.0, factor))
        self._fixture.set_dim(self._dim)

    def update(self, now_ms):
        """Advance the current scene and flush to hardware. Call every loop tick."""
        self._fixture.update(now_ms)
        if self._network:
            msg = self._network.tick(
                self._theme_idx,
                self._scene_idxs[self._theme_idx],
                self._network_dim(),
                now_ms,
            )
            if msg:
                msg_type = msg.get('type')
                if msg_type in ('heartbeat', 'change'):
                    self._apply_network_state(msg.get('theme', 0), msg.get('scene', 0), now_ms)
                    if not self._is_soloist:
                        self.set_dim(msg.get('dim', 1.0))
                elif msg_type in ('solo', 'dim'):
                    self._handle_dim_msg(msg)
        if self._save_pending and time.ticks_diff(now_ms, self._save_after) >= 0:
            self._save_pending = False
            storage.save({'theme': self._theme_idx, 'scenes': self._scene_idxs})

    def apply_state(self, theme_idx, scene_idx, now_ms, dim=1.0):
        self._apply_network_state(theme_idx, scene_idx, now_ms)
        if not self._is_soloist:
            self.set_dim(dim)

    def _network_dim(self):
        """Dim level to broadcast in outgoing messages.
        Soloists broadcast solo_dim_target so followers know what level to use,
        not their own dim (1.0) which would incorrectly restore followers."""
        return self._solo_dim_target if self._is_soloist else self._dim

    def _handle_dim_msg(self, msg):
        msg_type = msg.get('type')
        if msg_type == 'solo':
            if msg.get('active', False):
                self._is_soloist = False
                self._solo_active = True
                self._solo_dim_target = msg.get('dim', self._solo_dim)
                self.set_dim(self._solo_dim_target)
            else:
                self._is_soloist = False
                self._solo_active = False
                self.set_dim(1.0)
        elif msg_type == 'dim':
            if not self._is_soloist:
                self.set_dim(msg.get('dim', 1.0))

    def _apply_network_state(self, theme_idx, scene_idx, now_ms):
        theme_idx = min(theme_idx, len(self._themes) - 1)
        theme_changed = theme_idx != self._theme_idx
        if theme_changed:
            self._theme_idx = theme_idx
            self._load_scenes()
        scene_idx = min(scene_idx, len(self._scenes) - 1)
        scene_changed = scene_idx != self._scene_idxs[self._theme_idx]
        if scene_changed:
            self._scene_idxs[self._theme_idx] = scene_idx
        if theme_changed or scene_changed:
            self._play_current(now_ms)
            self._schedule_save(now_ms)

    def _load_scenes(self):
        self._scenes = self._themes[self._theme_idx].scenes()
        for name, scene in self._scenes:
            self._fixture.add_scene(name, scene)

    def _play_current(self, now_ms):
        name, _ = self._scenes[self._scene_idxs[self._theme_idx]]
        self._fixture.play(name, now_ms)

    def _schedule_save(self, now_ms):
        self._save_pending = True
        self._save_after = time.ticks_add(now_ms, self._save_delay_ms)
