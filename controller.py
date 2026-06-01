import time
import random
import storage
from patterns import SolidPattern, UniformScene


class Controller:
    """Manages themes and scenes for a fixture.

    Short press cycles scenes within the current theme.
    Long press advances to the next theme and resets to scene 0.
    State is saved to flash after save_delay_ms following the last button event.
    Dim is a network-level ceiling applied to all strips; it is not persisted.

    Network packets use theme and scene names (strings) rather than indices so
    controllers with different firmware versions can still interoperate. A
    controller that receives an unknown theme name displays a solid fallback
    color derived from the sender's representative_color() if one is provided.

    Solo mode: the soloist stays at full brightness and broadcasts solo_dim to
    all other controllers. Heartbeats carry the dim level followers should use
    (_network_dim), not the sender's own dim, so the soloist's heartbeats don't
    accidentally restore followers to full brightness.

    Leader election: if no heartbeat arrives within election_timeout_ms at boot,
    this controller declares itself leader. If two controllers declare simultaneously
    the one with the lower MAC address wins — the other stands down on receiving
    a leader heartbeat with a lower MAC. At runtime, if no leader heartbeat arrives
    for leader_reelect_ms, any controller may trigger a new election.
    """

    def __init__(self, fixture, themes, network=None,
                 solo_dim=0.2, save_delay_ms=2000,
                 election_timeout_ms=5000, leader_reelect_ms=10000):
        self._fixture = fixture
        self._themes = themes
        self._network = network
        self._solo_dim = solo_dim
        self._save_delay_ms = save_delay_ms
        self._election_timeout_ms = election_timeout_ms
        self._leader_reelect_ms = leader_reelect_ms
        self._save_pending = False
        self._save_after = 0
        self._scenes = []
        self._dim = 1.0
        self._is_soloist = False
        self._solo_active = False
        self._solo_dim_target = solo_dim
        self._is_leader = False
        self._ota_requested = False

        state = storage.load({'theme': 0, 'scenes': [0] * len(themes)})
        self._theme_idx = min(state['theme'], len(themes) - 1)
        self._scene_idxs = state['scenes']
        if len(self._scene_idxs) < len(themes):
            self._scene_idxs += [0] * (len(themes) - len(self._scene_idxs))
        for i, theme in enumerate(themes):
            limit = len(theme.scenes())
            self._scene_idxs[i] = min(self._scene_idxs[i], limit - 1)
        self._load_scenes()

    @property
    def is_leader(self):
        return self._is_leader

    @property
    def ota_requested(self):
        """True if an ota_update message arrived. Clears on read."""
        flag = self._ota_requested
        self._ota_requested = False
        return flag

    def status(self):
        """Return current controller state as a dict for the control panel."""
        return {
            'theme':      self._theme_name(),
            'scene':      self._scene_name(),
            'dim':        self._dim,
            'solo_active': self._solo_active,
            'is_soloist': self._is_soloist,
            'leader':     self._is_leader,
        }

    def start(self, now_ms, button=None):
        """Wait for network sync then play the initial scene.

        Uses tick() so heartbeat_request messages are properly handled during
        the wait. If no heartbeat arrives within election_timeout_ms, this
        controller declares itself leader (it's first on the network).

        Button is locked out once a network sync message arrives so a
        simultaneous press can't override network data.
        """
        if self._network and button:
            synced = False
            election_deadline = time.ticks_add(now_ms, self._election_timeout_ms)

            while True:
                now_ms = time.ticks_ms()
                msg = self._network.tick(
                    self._theme_name(),
                    self._scene_name(),
                    self._network_dim(),
                    now_ms,
                    color=self._theme_color(),
                )
                if msg:
                    msg_type = msg.get('type')
                    if msg_type in ('heartbeat', 'change'):
                        color = msg.get('color')
                        self._apply_network_state(
                            msg.get('theme'), msg.get('scene'), now_ms,
                            color=tuple(color) if color else None,
                        )
                        if not self._is_soloist:
                            self.set_dim(msg.get('dim', 1.0))
                        self._handle_leader_heartbeat(msg, now_ms)
                        synced = True
                        break
                    elif msg_type in ('solo', 'dim'):
                        self._handle_dim_msg(msg)

                if time.ticks_diff(now_ms, election_deadline) >= 0:
                    self._become_leader(now_ms)
                    break

                if not synced and button.update(now_ms):
                    break

            self._network.announce()
        self._play_current(now_ms)

    def next_scene(self, now_ms):
        self._scene_idxs[self._theme_idx] = (self._scene_idxs[self._theme_idx] + 1) % len(self._scenes)
        self._play_current(now_ms)
        self._schedule_save(now_ms)
        if self._network:
            self._network.send_change(
                self._theme_name(), self._scene_name(),
                self._network_dim(), color=self._theme_color(),
            )

    def next_theme(self, now_ms):
        self._theme_idx = (self._theme_idx + 1) % len(self._themes)
        self._load_scenes()
        self._play_current(now_ms)
        self._schedule_save(now_ms)
        if self._network:
            self._network.send_change(
                self._theme_name(), self._scene_name(),
                self._network_dim(), color=self._theme_color(),
            )

    def broadcast_theme_random(self, now_ms):
        """Broadcast the current theme with no scene. Each receiver independently
        picks a random scene from that theme."""
        if self._network:
            self._network.send_change(
                self._theme_name(), None,
                self._network_dim(), color=self._theme_color(),
            )

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

    def update(self, now_ms, bridge=None):
        """Advance the current scene and flush to hardware. Call every loop tick."""
        self._fixture.update(now_ms)
        if self._network:
            msg = self._network.tick(
                self._theme_name(),
                self._scene_name(),
                self._network_dim(),
                now_ms,
                color=self._theme_color(),
            )
            if msg and bridge:
                bridge.forward(msg)
            if msg:
                msg_type = msg.get('type')
                if msg_type in ('heartbeat', 'change'):
                    color = msg.get('color')
                    self._apply_network_state(
                        msg.get('theme'), msg.get('scene'), now_ms,
                        color=tuple(color) if color else None,
                    )
                    if not self._is_soloist:
                        self.set_dim(msg.get('dim', 1.0))
                    self._handle_leader_heartbeat(msg, now_ms)
                elif msg_type in ('solo', 'dim'):
                    self._handle_dim_msg(msg)
                elif msg_type == 'ota_update':
                    self._ota_requested = True

            # Re-election if leader has gone offline
            if not self._is_leader:
                age = self._network.leader_heartbeat_age(now_ms)
                if age is not None and age >= self._leader_reelect_ms:
                    self._become_leader(now_ms)

        if self._save_pending and time.ticks_diff(now_ms, self._save_after) >= 0:
            self._save_pending = False
            storage.save({'theme': self._theme_idx, 'scenes': self._scene_idxs})

    def _become_leader(self, now_ms):
        self._is_leader = True
        if self._network:
            self._network.is_leader = True

    def _handle_leader_heartbeat(self, msg, now_ms):
        """Handle the leader flag in an incoming heartbeat. If the sender is also
        a leader but has a lower MAC, we stand down — lower MAC wins the election."""
        if not msg.get('leader'):
            return
        sender = msg.get('sender', '')
        self._network.note_leader_heartbeat(sender, now_ms)
        if self._is_leader and sender < self._network.mac:
            self._is_leader = False
            self._network.is_leader = False

    def _theme_name(self):
        return self._themes[self._theme_idx].name

    def _scene_name(self):
        return self._scenes[self._scene_idxs[self._theme_idx]][0]

    def _theme_color(self):
        return self._themes[self._theme_idx].representative_color()

    def _network_dim(self):
        """Dim level to broadcast — soloists send solo_dim_target so followers
        know what level to use, not 1.0 which would incorrectly restore them."""
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

    def _apply_network_state(self, theme_name, scene_name, now_ms, color=None):
        """Apply incoming theme/scene by name. Falls back to a solid color scene
        if the theme name isn't recognised on this controller."""
        theme_idx = next(
            (i for i, t in enumerate(self._themes) if t.name == theme_name), None
        )

        if theme_idx is None:
            if color is not None:
                self._fixture.add_scene('_fallback', UniformScene(SolidPattern(color)))
                self._fixture.play('_fallback', now_ms)
            return

        theme_changed = theme_idx != self._theme_idx
        if theme_changed:
            self._theme_idx = theme_idx
            self._load_scenes()

        if scene_name is None:
            scene_idx = random.randint(0, len(self._scenes) - 1)
        else:
            scene_idx = next(
                (i for i, (n, _) in enumerate(self._scenes) if n == scene_name), 0
            )
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
