"""Follower-side channel recovery (non-leaders only).

Two cases, both needing a one-off WiFi scan (the sanctioned blocking exception):
  - orphan: heard nothing for too long → likely left on a stale channel after
    the mesh migrated; rescan, re-pin, re-announce.
  - wake:   freshly booted into an autonomous mesh → scan once and, if a hotspot
    exists, alert the leader so it resumes connecting.
"""
import time

from config import DEFAULT_CHANNEL
from secrets import OTA_SSID
from mesh import scan_channel
import log as _log

ORPHAN_SILENCE_MS   = 15000
WAKE_SCAN_WINDOW_MS = 30000


class FollowerRecovery:
    def __init__(self, now_ms):
        self._boot_ms          = now_ms
        self._last_recovery_ms = now_ms
        self._wake_scanned     = False

    def tick(self, controller, mesh, now_ms):
        if controller.is_leader:
            return
        self._orphan_rescan(mesh, now_ms)
        self._wake_scan(mesh, now_ms)

    def _orphan_rescan(self, mesh, now_ms):
        if mesh.silent_for(now_ms) <= ORPHAN_SILENCE_MS:
            return
        if time.ticks_diff(now_ms, self._last_recovery_ms) <= ORPHAN_SILENCE_MS:
            return
        self._last_recovery_ms = now_ms
        ch = scan_channel(OTA_SSID)
        mesh.apply_channel(ch if ch is not None else DEFAULT_CHANNEL)
        mesh.announce()
        _log.write('main', 'orphan recovery rescan', level='warn')

    def _wake_scan(self, mesh, now_ms):
        if self._wake_scanned or not mesh.mesh_autonomous:
            return
        if time.ticks_diff(now_ms, self._boot_ms) >= WAKE_SCAN_WINDOW_MS:
            return
        self._wake_scanned = True
        ch = scan_channel(OTA_SSID)
        if ch is not None:
            mesh.send_hotspot_found(ch)
            _log.write('main', 'found hotspot while autonomous, alerting leader')
