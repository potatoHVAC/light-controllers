import time
import random
import storage
from patterns import SolidPattern, UniformScene

IDENTIFY_COLOR = (180, 60, 0)   # orange identify blink
IDENTIFY_LEDS  = 3              # first N LEDs of the primary strip
IDENTIFY_BLINK_MS = 200


def _parse_color(value):
    """Parse a '#rrggbb' (or 'rrggbb') string to an (r, g, b) tuple, else None."""
    if not value:
        return None
    if isinstance(value, (tuple, list)):
        return tuple(value)
    s = value.lstrip('#')
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


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
                 election_timeout_ms=5000, leader_reelect_ms=10000,
                 solo_release_fade_ms=1000, identify_ms=2000,
                 personal_default=None):
        self._fixture = fixture
        self._themes = themes
        self._network = network
        self._solo_dim = solo_dim
        self._save_delay_ms = save_delay_ms
        self._election_timeout_ms = election_timeout_ms
        self._leader_reelect_ms = leader_reelect_ms
        self._solo_release_fade_ms = solo_release_fade_ms
        self._identify_ms = identify_ms
        self._personal_default = personal_default or {}
        self._save_pending = False
        self._save_after = 0
        self._scenes = []
        self._dim = 1.0                # the brightness actually applied to strips
        self._master_dim = 1.0         # master-dimmer level (the soloist's ceiling)
        self._is_soloist = False
        self._solo_active = False
        self._solo_bg = solo_dim       # non-soloist level as a fraction of master
        self._solo_dim_target = solo_dim
        self._last_solo_hb_ms = None   # tracks last heartbeat carrying solo dim
        self._is_leader = False
        self._ota_requested = False
        self._ota_queued = False
        self._ota_queue_ms = 0
        self._reboot_requested = False
        self._personal_mode = False    # True after apply_default; heartbeats don't override
        self._identify_until_ms = None
        # Dim fade state (used when releasing solo). _fade_dur == 0 means idle.
        self._fade_from = 1.0
        self._fade_to = 1.0
        self._fade_start_ms = 0
        self._fade_dur = 0

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
    def theme(self):
        return self._theme_name()

    @property
    def scene(self):
        return self._scene_name()

    @property
    def dim(self):
        return self._dim

    @property
    def master_dim(self):
        return self._master_dim

    def queue_ota(self, now_ms):
        """Leader-only: defer this controller's own OTA so followers get a head
        start. The leader relays the command to the mesh immediately and holds
        for OTA_LEADER_WAIT_MS before starting its own download."""
        self._ota_queued    = True
        self._ota_queue_ms  = now_ms

    def ota_due(self, now_ms, wait_ms):
        """True once the leader's deferred OTA hold has elapsed."""
        return self._ota_queued and time.ticks_diff(now_ms, self._ota_queue_ms) >= wait_ms

    @property
    def ota_requested(self):
        """True if an ota_update message arrived. Clears on read."""
        flag = self._ota_requested
        self._ota_requested = False
        return flag

    @property
    def reboot_requested(self):
        """True if a config change needs a reboot to apply. Clears on read."""
        flag = self._reboot_requested
        self._reboot_requested = False
        return flag

    def _targeted(self, msg):
        """A targeted message applies only to this controller (or to all when
        no target is given)."""
        t = msg.get('target')
        return t is None or (self._network is not None and t == self._network.mac)

    def apply_identify(self, now_ms):
        """Blink the first few LEDs orange for a few seconds to locate this unit."""
        self._identify_until_ms = time.ticks_add(now_ms, self._identify_ms)

    def apply_default(self, now_ms):
        """Go to this controller's stored personal default theme/scene/color.
        Enters personal mode so heartbeats from other controllers (which may
        have different personal defaults) don't immediately override this state.
        Personal mode clears on the next explicit change command."""
        d = self._personal_default
        if d.get('default_theme'):
            color = d.get('default_color')
            self._apply_network_state(
                d['default_theme'], d.get('default_scene'), now_ms,
                color=_parse_color(color),
            )
        # Always enter personal mode — even with no configured defaults — so
        # heartbeats from other controllers showing their own personal defaults
        # don't override what this controller is currently displaying.
        self._personal_mode = True

    def apply_set_config(self, config):
        """Persist a pushed config and request a reboot to apply it."""
        if config:
            import device_config
            device_config.save(config)
            self._reboot_requested = True

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

    def begin(self, now_ms):
        """Start the (non-blocking) sync/election phase. Call once, then call
        tick_start() each tick until it returns True. The strips stay dark until
        startup completes (synced from the mesh, elected leader, or button)."""
        self._synced = False
        self._election_deadline = time.ticks_add(now_ms, self._election_timeout_ms)

    def tick_start(self, now_ms, button_pressed=False):
        """Advance startup one step. Returns True when startup is complete.

        Syncs from the first heartbeat/change, or declares itself leader if no
        heartbeat arrives within election_timeout_ms, or starts immediately on a
        button press. Button is locked out once a sync message has arrived."""
        if not self._network:
            self._finish_start(now_ms)
            return True

        msg = self._network.tick(
            self._theme_name(), self._scene_name(),
            self._network_dim(), now_ms, color=self._theme_color(),
            master_dim=self._master_dim,
            personal=self._personal_mode,
        )
        if msg:
            msg_type = msg.get('type')
            if msg_type in ('heartbeat', 'change'):
                color = msg.get('color')
                if msg.get('personal') and not self._personal_mode:
                    # Booting into a mesh already in personal mode — apply own
                    # defaults rather than snapping to the sender's personal theme.
                    # This is safe here because tick_start() fires only once at boot;
                    # it is NOT in the steady-state loop so there is no re-infection risk.
                    self.apply_default(now_ms)
                else:
                    self._apply_network_state(
                        msg.get('theme'), msg.get('scene'), now_ms,
                        color=tuple(color) if color else None,
                    )
                if not self._is_soloist:
                    self.set_master_dim(msg.get('master_dim', msg.get('dim', 1.0)))
                self._handle_leader_heartbeat(msg, now_ms)
                self._finish_start(now_ms)
                return True
            elif msg_type in ('solo', 'dim'):
                self._handle_dim_msg(msg, now_ms)

        if time.ticks_diff(now_ms, self._election_deadline) >= 0:
            self._become_leader(now_ms)
            self._finish_start(now_ms)
            return True

        if not self._synced and button_pressed:
            self._finish_start(now_ms)
            return True

        return False

    def _finish_start(self, now_ms):
        if self._network:
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

    def solo(self, bg=None):
        """Become the soloist: stay at the master-dim level, dim all others to a
        fraction of it. bg is that fraction (0..1); defaults to the configured
        solo_dim. The soloist does NOT jump to full brightness — it respects the
        master dimmer."""
        frac = self._solo_dim if bg is None else max(0.0, min(1.0, bg))
        self._is_soloist = True
        self._solo_active = True
        self._solo_bg = frac
        self._solo_dim_target = self._master_dim * frac   # absolute level for others
        self._fade_dur = 0            # cancel any in-progress release fade
        self.set_dim(self._master_dim)
        if self._network:
            self._network.send_solo(active=True, dim=self._solo_dim_target)

    def release_solo(self):
        """Release solo: fade back to the master-dim level across the mesh."""
        self._is_soloist = False
        self._solo_active = False
        self._start_release_fade(time.ticks_ms())
        if self._network:
            self._network.send_solo(active=False)

    def apply_solo_tag(self, tag, frac, active, now_ms):
        """Tag-group solo: every controller decides locally. If this controller's
        tag list contains `tag` it becomes a soloist at the master level; all others
        dim to `frac` of master. `frac` is a fraction (0..1); defaults to solo_dim.
        active=False releases (same as a normal solo release)."""
        if not active:
            self._is_soloist = False
            self._solo_active = False
            self._start_release_fade(now_ms)
            return
        frac = self._solo_dim if frac is None else max(0.0, min(1.0, frac))
        in_group = tag in (self._personal_default.get('tags') or [])
        self._solo_active = True
        self._fade_dur = 0
        self._solo_bg = frac
        self._solo_dim_target = self._master_dim * frac   # the follower level
        if in_group:
            self._is_soloist = True
            self.set_dim(self._master_dim)
        else:
            self._is_soloist = False
            self.set_dim(self._solo_dim_target)

    def set_dim(self, factor):
        """Apply a brightness ceiling to all strips (the value actually shown)."""
        self._dim = max(0.0, min(1.0, factor))
        self._fixture.set_dim(self._dim)

    def set_master_dim(self, factor):
        """Set the master-dimmer level. Applied immediately unless this controller
        is currently a dimmed non-soloist (it holds the solo background level until
        the soloist re-broadcasts). The soloist rescales and re-announces so its
        followers track the new master level."""
        self._master_dim = max(0.0, min(1.0, factor))
        if self._fade_dur > 0:
            self._fade_to = self._master_dim     # redirect an in-progress fade
            return
        if self._is_soloist:
            self.set_dim(self._master_dim)
            self._solo_dim_target = self._master_dim * self._solo_bg
            if self._network:
                self._network.send_solo(active=True, dim=self._solo_dim_target)
        elif not self._solo_active:
            self.set_dim(self._master_dim)

    def _start_release_fade(self, now_ms):
        """Begin a non-blocking fade from the current dim up to the master level."""
        if self._solo_release_fade_ms <= 0:
            self.set_dim(self._master_dim)
            return
        self._fade_from     = self._dim
        self._fade_to       = self._master_dim
        self._fade_start_ms = now_ms
        self._fade_dur      = self._solo_release_fade_ms

    def _apply_fade(self, now_ms):
        if self._fade_dur <= 0:
            return
        t = time.ticks_diff(now_ms, self._fade_start_ms)
        if t >= self._fade_dur:
            self.set_dim(self._fade_to)
            self._fade_dur = 0
        else:
            frac = t / self._fade_dur
            self.set_dim(self._fade_from + (self._fade_to - self._fade_from) * frac)

    def _render_identify(self, now_ms):
        """Overlay the identify blink on top of the running pattern.

        The normal pattern renders and shows first (the rest of the strip stays
        live). Then we overwrite the first few LEDs with the orange blink and
        call show() again — the brief intermediate state is imperceptible."""
        strip = self._fixture.strips[0]
        color = IDENTIFY_COLOR if (now_ms // IDENTIFY_BLINK_MS) % 2 == 0 else (0, 0, 0)
        for i in range(min(IDENTIFY_LEDS, strip.num_leds)):
            strip[i] = color
        strip.show()

    def update(self, now_ms):
        """Advance the current scene and flush to hardware. Call every loop tick.
        Returns the raw mesh message received this tick (or None) so the caller
        can forward it to the bridge without coupling mesh to bridge."""
        self._fixture.update(now_ms)
        if self._identify_until_ms is not None:
            if time.ticks_diff(now_ms, self._identify_until_ms) < 0:
                self._render_identify(now_ms)   # overlay blink on top of pattern
            else:
                self._identify_until_ms = None
        received = None
        if self._network:
            msg = self._network.tick(
                self._theme_name(),
                self._scene_name(),
                self._network_dim(),
                now_ms,
                color=self._theme_color(),
                master_dim=self._master_dim,
                personal=self._personal_mode,
            )
            if msg:
                received = msg
                msg_type = msg.get('type')
                if msg_type in ('heartbeat', 'change'):
                    color = msg.get('color')
                    if msg_type == 'change':
                        # Explicit change command — always apply and exit personal mode.
                        self._personal_mode = False
                        self._apply_network_state(
                            msg.get('theme'), msg.get('scene'), now_ms,
                            color=tuple(color) if color else None,
                        )
                    elif not self._personal_mode:
                        self._apply_network_state(
                            msg.get('theme'), msg.get('scene'), now_ms,
                            color=tuple(color) if color else None,
                        )
                    if not self._is_soloist and self._fade_dur <= 0:
                        incoming_dim    = msg.get('dim', 1.0)
                        incoming_master = msg.get('master_dim', incoming_dim)
                        # Every heartbeat carries both dim (the current applied
                        # level — may be the solo background) and master_dim (the
                        # true ceiling). During solo, only trust a heartbeat if the
                        # sender is itself dimmed (dim < master_dim), meaning they
                        # received the solo packet. Ignore full-brightness heartbeats
                        # from controllers that missed it — otherwise they restore us
                        # to full. Outside solo, both values are the master level.
                        if self._solo_active:
                            if incoming_dim < incoming_master:
                                self.set_dim(incoming_dim)
                                self._last_solo_hb_ms = now_ms
                        else:
                            self.set_dim(incoming_dim)
                            self._master_dim = incoming_master
                    self._handle_leader_heartbeat(msg, now_ms)
                elif msg_type in ('solo', 'dim'):
                    self._handle_dim_msg(msg, now_ms)
                elif msg_type == 'ota_update':
                    if self._targeted(msg):
                        self._ota_requested = True
                elif msg_type == 'identify':
                    if self._targeted(msg):
                        self.apply_identify(now_ms)
                elif msg_type == 'solo_request':
                    if self._targeted(msg):
                        self.solo(msg.get('dim'))
                elif msg_type == 'solo_tag':
                    self.apply_solo_tag(msg.get('tag'), msg.get('dim'),
                                        msg.get('active', True), now_ms)
                elif msg_type == 'force_leader':
                    target = msg.get('target')
                    if self._network and target == self._network.mac:
                        self.force_leader()
                    elif self._is_leader:
                        self.step_down()
                elif msg_type == 'default':
                    self.apply_default(now_ms)
                elif msg_type == 'set_config':
                    if self._targeted(msg):
                        self.apply_set_config(msg.get('config'))

            # Re-election if leader has gone offline
            if not self._is_leader:
                age = self._network.leader_heartbeat_age(now_ms)
                if age is not None and age >= self._leader_reelect_ms:
                    self._become_leader(now_ms)

            # Auto-release solo if soloist heartbeats have gone silent
            if self._solo_active and not self._is_soloist and self._last_solo_hb_ms is not None:
                if time.ticks_diff(now_ms, self._last_solo_hb_ms) >= self._leader_reelect_ms:
                    self._solo_active = False
                    self._last_solo_hb_ms = None
                    self.set_dim(1.0)

        self._apply_fade(now_ms)

        if self._save_pending and time.ticks_diff(now_ms, self._save_after) >= 0:
            self._save_pending = False
            storage.save({'theme': self._theme_idx, 'scenes': self._scene_idxs})
        return received

    def _become_leader(self, now_ms):
        self._is_leader = True
        if self._network:
            self._network.is_leader = True

    def force_leader(self):
        """Forced to become leader by the control plane (admin 'Make Leader').
        Acts like winning a fresh election — the current leader stands down on
        the same broadcast. Reelection is unaffected if this controller later dies."""
        self._is_leader = True
        if self._network:
            self._network.is_leader = True

    def step_down(self):
        """Give up leadership (another controller was forced to lead). The bridge
        is released by LeaderLink once it sees is_leader go False."""
        self._is_leader = False
        if self._network:
            self._network.is_leader = False

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

    def _handle_dim_msg(self, msg, now_ms):
        msg_type = msg.get('type')
        if msg_type == 'solo':
            if msg.get('active', False):
                self._is_soloist = False
                self._solo_active = True
                # The soloist already scaled by master, so this is absolute.
                self._solo_dim_target = msg.get('dim', self._master_dim * self._solo_dim)
                self._fade_dur = 0                 # cancel any release fade
                self.set_dim(self._solo_dim_target)
            else:
                self._is_soloist = False
                self._solo_active = False
                self._start_release_fade(now_ms)   # fade back to master level
        elif msg_type == 'dim':
            self.set_master_dim(msg.get('dim', 1.0))

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
