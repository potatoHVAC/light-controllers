"""The leader's bridge lifecycle: connect with backoff, declare the mesh
autonomous when no server is found, give up after enough failures, and resume
when a follower reports a hotspot. Only meaningful while this controller leads.

Kept out of main.py so the loop stays readable and this logic is testable.
"""
import time

from config import (BRIDGE_RETRY_INIT_MS, BRIDGE_RETRY_MAX_MS,
                    BRIDGE_AUTONOMOUS_AFTER_MS, BRIDGE_CAP_RETRIES)
import log as _log

_SELF_HB_MS = 5000   # how often the leader forwards its own state to the server


class LeaderLink:
    def __init__(self, mesh):
        self._mesh        = mesh
        self.bridge       = None
        self._retry_at    = 0                    # earliest time to try again
        self._retry_ms    = BRIDGE_RETRY_INIT_MS  # backoff, doubles each failure
        self._cap_fails   = 0                    # failures at the cap interval
        self._gave_up     = False                # stopped scanning until an alert
        self._hint_ch     = None                 # channel from a hotspot_found alert
        self._self_hb_at  = 0                    # last self-heartbeat forward time

    def make_bridge(self):
        """Create the bridge now (called if already leader at boot)."""
        from bridge import Bridge
        self.bridge = Bridge(self._mesh)

    def connected(self):
        return self.bridge is not None and self.bridge.is_connected()

    def forward(self, received):
        """Forward a received mesh packet to the server, if connected."""
        if self.connected() and received:
            self.bridge.forward(received)

    def on_alert(self, controller, received, now_ms):
        """A follower found a hotspot — resume connecting, even after giving up."""
        if not (received and controller.is_leader
                and received.get('type') == 'hotspot_found'):
            return
        self._gave_up   = False
        self._cap_fails = 0
        self._retry_ms  = BRIDGE_RETRY_INIT_MS
        self._retry_at  = now_ms
        self._hint_ch   = received.get('ch')
        _log.write('main', 'hotspot alert received, resuming bridge')

    def tick(self, controller, now_ms):
        """Advance the bridge one step. Returns a server command to run, or None."""
        if controller.is_leader and not self._gave_up:
            self._advance_connect(now_ms)
        cmd = self._service(now_ms)
        if controller.is_leader and self.connected():
            self._maybe_forward_self(controller, now_ms)
        return cmd

    # ── internals ────────────────────────────────────────────────────────────

    def _advance_connect(self, now_ms):
        if self.bridge is None:
            if time.ticks_diff(now_ms, self._retry_at) >= 0:
                from bridge import Bridge
                self.bridge = Bridge(self._mesh)
                if self._hint_ch is not None:
                    self.bridge.set_channel_hint(self._hint_ch)
                    self._hint_ch = None
            return

        result = self.bridge.tick_connect(now_ms)
        if result is True:
            self._on_connected()
        elif result is False:
            self._on_failed(now_ms)

    def _on_connected(self):
        _log.write('main', 'bridge connected')
        self._retry_ms  = BRIDGE_RETRY_INIT_MS
        self._cap_fails = 0
        self._mesh.set_autonomous(False)
        self._flush_log_buffer()

    def _on_failed(self, now_ms):
        failed_interval = self._retry_ms
        if failed_interval >= BRIDGE_RETRY_MAX_MS:
            self._cap_fails += 1
        if failed_interval >= BRIDGE_AUTONOMOUS_AFTER_MS and not self._mesh.autonomous:
            self._mesh.set_autonomous(True)
            _log.write('main', 'no server yet, declaring autonomous', level='warn')
        self._retry_ms = min(self._retry_ms * 2, BRIDGE_RETRY_MAX_MS)
        self._retry_at = time.ticks_add(now_ms, self._retry_ms)
        self.bridge = None
        if self._cap_fails >= BRIDGE_CAP_RETRIES:
            self._gave_up = True
            _log.write('main', 'no server found, stopped scanning', level='warn')

    def _service(self, now_ms):
        if not self.connected():
            return None
        if not self.bridge.check_server_alive(now_ms):
            _log.write('main', 'server heartbeat lost, reconnecting', level='warn')
            self.bridge     = None
            self._retry_ms  = BRIDGE_RETRY_INIT_MS
            self._cap_fails = 0
            self._retry_at  = time.ticks_add(now_ms, BRIDGE_RETRY_INIT_MS)
            return None
        return self.bridge.tick()

    def _maybe_forward_self(self, controller, now_ms):
        """Forward the leader's own state so it appears in the server registry."""
        if time.ticks_diff(now_ms, self._self_hb_at) < _SELF_HB_MS:
            return
        self._self_hb_at = now_ms
        self.bridge.forward({
            'type':   'heartbeat',
            'sender': self._mesh.mac,
            'theme':  controller.theme,
            'scene':  controller.scene,
            'dim':    controller.dim,
            'fw':     self._mesh._fw,
            'cfg':    self._mesh._cfg,
            'leader': True,
        })

    def _flush_log_buffer(self):
        """Send the local log buffer so autonomous-lifecycle events that
        happened while disconnected reach the server."""
        for e in _log.get_entries():
            self.bridge.forward({'type': 'log', 'sender': self._mesh.mac,
                                 'src': e['src'], 'lvl': e['lvl'], 'msg': e['msg']})
