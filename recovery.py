"""Controller-side recovery when the mesh loses its bridge to the server.

Two systems:

FollowerRecovery — orphan detection only.
  A follower that hears nothing for too long has likely drifted to a stale
  channel. It rescans and re-announces so it can rejoin the mesh.

BridgeRecovery — autonomous-mode recovery.
  When the leader gives up finding the server it declares the mesh autonomous.
  This class gives non-leader controllers a chance to establish the bridge
  themselves before the rig is fully on its own:

  Normal followers: 2 immediate attempts the moment they boot into an
    already-autonomous mesh. Both happen as fast as possible. If neither
    connects they give up and run autonomously.

  Leader-tagged controllers: treated as the best candidate for the bridge.
    They try twice with random 5–60s spacing whenever they hear autonomous
    mode activate. If autonomous clears and comes back they try again.

  On success: the controller stays leader and normal MAC-tiebreak election
    handles handing off to a better-priority unit when one appears.
  On failure after both attempts: return to follower, join autonomous mode.
"""
import time

from config import DEFAULT_CHANNEL
from secrets import OTA_SSID
from mesh import scan_channel
import log as _log

ORPHAN_SILENCE_MS       = 15000
BRIDGE_ATTEMPT_TIMEOUT  = 20000   # per attempt: time to wait for bridge to connect


class FollowerRecovery:
    """Orphan-channel rescan only. Bridge recovery is handled by BridgeRecovery."""

    def __init__(self, now_ms):
        self._last_recovery_ms = now_ms

    def tick(self, controller, mesh, now_ms):
        if controller.is_leader:
            return
        if mesh.silent_for(now_ms) <= ORPHAN_SILENCE_MS:
            return
        if time.ticks_diff(now_ms, self._last_recovery_ms) <= ORPHAN_SILENCE_MS:
            return
        self._last_recovery_ms = now_ms
        ch = scan_channel(OTA_SSID)
        mesh.apply_channel(ch if ch is not None else DEFAULT_CHANNEL)
        mesh.announce()
        _log.write('main', 'orphan recovery rescan', level='warn')


class BridgeRecovery:
    """Attempt to establish the bridge when the mesh is in autonomous mode."""

    def __init__(self, is_leader_tagged):
        self._tagged          = is_leader_tagged
        self._attempts        = 0
        self._attempt_start   = None   # ticks_ms when current attempt began
        self._fire_at         = None   # ticks_ms when next attempt should start
        self._done            = False  # True once both attempts are exhausted
        self._was_autonomous  = False

    def tick(self, controller, link, mesh, now_ms):
        autonomous = mesh.mesh_autonomous

        # Leader-tagged: reset when autonomous clears so we'll try again next time.
        if self._tagged and self._was_autonomous and not autonomous:
            self._reset()
        self._was_autonomous = autonomous

        # Nothing to do if we have a leader already, or gave up, or not autonomous.
        if controller.is_leader or self._done or not autonomous:
            return

        # An attempt is in progress — monitor it.
        if self._attempt_start is not None:
            if not controller.is_leader:
                # Lost leadership mid-attempt (MAC tiebreak) — counts as a failure.
                self._attempt_start = None
                self._schedule_next(now_ms)
                return

            if link.connected():
                # Bridge connected — stay leader, we're done.
                self._done = True
                _log.write('main', 'bridge recovery connected, acting as temporary leader')
                return

            if time.ticks_diff(now_ms, self._attempt_start) >= BRIDGE_ATTEMPT_TIMEOUT:
                # Timed out — release and either retry or give up.
                link.surrender()
                controller.step_down()
                self._attempt_start = None
                self._schedule_next(now_ms)
            return

        # No attempt running — start one when it's time.
        if self._fire_at is None:
            self._arm(now_ms)
            return

        if time.ticks_diff(now_ms, self._fire_at) < 0:
            return   # not yet

        if self._attempts < 2:
            controller.force_leader()
            self._attempt_start = now_ms
            self._attempts += 1
            _log.write('main', f'bridge recovery attempt {self._attempts}')

    # ── internals ────────────────────────────────────────────────────────────

    def _arm(self, now_ms):
        """Set the fire time for the next attempt."""
        if self._tagged:
            import random
            self._fire_at = time.ticks_add(now_ms, random.randint(5000, 60000))
        else:
            self._fire_at = now_ms   # normal follower: fire immediately

    def _schedule_next(self, now_ms):
        """After a failed attempt: schedule the next one, or mark done."""
        if self._attempts < 2:
            self._arm(now_ms)
        else:
            self._done = True
            _log.write('main', 'bridge recovery exhausted, joining autonomous', level='warn')

    def _reset(self):
        self._attempts       = 0
        self._attempt_start  = None
        self._fire_at        = None
        self._done           = False