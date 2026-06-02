import time
import os
from machine import Pin
from strip import Strip
from fixture import Fixture
from button import Button
from themes import RandomTheme, ColorTheme
from config import (THEMES as _THEME_DEFS, DEFAULT_CHANNEL,
                    BRIDGE_RETRY_INIT_MS, BRIDGE_RETRY_MAX_MS,
                    BRIDGE_AUTONOMOUS_AFTER_MS, BRIDGE_CAP_RETRIES)
from controller import Controller
from mesh import Mesh
import log as _log

# LED Brain: 2 strips × 3 LEDs
PRIMARY_PIN        = 26
SECONDARY_PIN      = 22
NUM_LEDS           = 3
BUTTON_PIN         = 33
BUTTON_SOLOIST_PIN = 27

_UPDATE_READY = '/update_ready'
_UPDATE_DIR   = '/update'


def _copy_file(src, dst):
    with open(src, 'rb') as sf, open(dst, 'wb') as df:
        while True:
            chunk = sf.read(512)
            if not chunk:
                break
            df.write(chunk)


def _copy_tree(src, dst, skip=None):
    """Recursively copy src directory into dst. dst='' means filesystem root.
    skip: filename to exclude (copied separately after everything else)."""
    for name in os.listdir(src):
        if name == skip:
            continue
        s = src + '/' + name
        d = ('/' + name) if not dst else (dst + '/' + name)
        try:
            os.listdir(s)  # raises OSError if s is a file
            try:
                os.mkdir(d)
            except OSError:
                pass
            _copy_tree(s, d)
        except OSError:
            _copy_file(s, d)


def _rm_tree(path):
    try:
        for f in os.listdir(path):
            _rm_tree(path + '/' + f)
        os.rmdir(path)
    except OSError:
        os.remove(path)


# Apply any pending A/B update before anything else. The swap is retried on
# every boot until /update_ready is successfully removed, so a power cut
# mid-swap is safe — /update/ always holds the complete verified copy.
try:
    os.stat(_UPDATE_READY)
    _copy_tree(_UPDATE_DIR, '', skip='main.py')
    _copy_file(_UPDATE_DIR + '/main.py', '/main.py')
    _rm_tree(_UPDATE_DIR)
    os.remove(_UPDATE_READY)  # removed LAST — if power cuts before this, swap retries
    import machine as _m
    _m.reset()
except OSError:
    # No marker — clean up any incomplete download.
    try:
        _rm_tree(_UPDATE_DIR)
    except OSError:
        pass


def _run_ota():
    """Download and stage an OTA update, then reboot to apply it."""
    import neopixel
    import machine
    np = neopixel.NeoPixel(Pin(PRIMARY_PIN), NUM_LEDS)
    from ota import run as ota_run
    if ota_run(np=np):
        machine.reset()
    del np


def _execute_bridge_command(cmd, ctrl, now_ms):
    """Execute a command received from the laptop bridge."""
    cmd_type = cmd.get('type')
    if cmd_type == 'change':
        color = cmd.get('color')
        ctrl._apply_network_state(
            cmd.get('theme'), cmd.get('scene'), now_ms,
            color=tuple(color) if color else None,
        )
        if ctrl._network:
            ctrl._network.send_change(
                cmd.get('theme'), cmd.get('scene'),
                ctrl._network_dim(), color=tuple(color) if color else None,
            )
    elif cmd_type == 'dim':
        dim = float(cmd.get('dim', 1.0))
        ctrl.set_dim(dim)
        if ctrl._network:
            ctrl._network.send_dim(dim)
    elif cmd_type == 'solo':
        if cmd.get('active', False):
            ctrl.solo()
        else:
            ctrl.release_solo()
    elif cmd_type == 'ota_update':
        if ctrl._network:
            ctrl._network.send_ota_update()
        _run_ota()


def main():
    strips = [
        Strip("primary",   PRIMARY_PIN,   NUM_LEDS),
        Strip("secondary", SECONDARY_PIN, NUM_LEDS),
    ]
    fixture = Fixture(strips)
    button        = Button(BUTTON_PIN)
    soloist_button = Button(BUTTON_SOLOIST_PIN)

    themes = []
    for td in _THEME_DEFS:
        if td['name'] == 'random':
            themes.append(RandomTheme())
        elif td.get('color'):
            themes.append(ColorTheme(tuple(td['color']), td['name']))

    fixture.clear()

    mesh = Mesh()
    _log.set_mesh(mesh)
    controller = Controller(fixture, themes, network=mesh)
    controller.start(time.ticks_ms(), button=button)

    # Bridge connection is non-blocking — tick_connect() advances the state
    # machine one step per loop iteration. The leader stays leader regardless
    # of bridge status. Backoff ramps up to the cap, declares the mesh
    # autonomous, then gives up after BRIDGE_CAP_RETRIES cap-interval failures.
    _bridge       = None
    _retry_at     = 0                     # 0 = attempt immediately
    _retry_ms     = BRIDGE_RETRY_INIT_MS  # current backoff, doubles on failure
    _cap_fails    = 0                     # failures at the cap interval
    _gave_up      = False                 # stopped scanning until a hotspot alert
    _hint_ch      = None                  # known channel from a hotspot_found alert
    _wake_scanned = False                 # one-shot boot scan when mesh autonomous

    if controller.is_leader:
        from bridge import Bridge
        _bridge = Bridge(mesh)

    # Orphan recovery: a follower that hears nothing for this long has likely
    # been left on a stale channel after the mesh migrated. It rescans for the
    # hotspot, re-pins, and re-announces. The leader never does this (a lone
    # leader is silent by design); only non-leaders, and only when truly silent.
    ORPHAN_SILENCE_MS = 15000
    _last_recovery_ms = time.ticks_ms()

    # The wake scan only fires for a freshly-booted controller (within this
    # window), so a long-running follower does not scan when the leader flips
    # to autonomous at the 5-minute mark — that would freeze every follower at once.
    WAKE_SCAN_WINDOW_MS = 30000
    _boot_ms = time.ticks_ms()

    while True:
        now_ms = time.ticks_ms()

        event = button.update(now_ms)
        if event == 'short':
            controller.next_scene(now_ms)
        elif event == 'long':
            controller.next_theme(now_ms)

        solo_event = soloist_button.update(now_ms)
        if solo_event == 'short':
            controller.solo()
        elif solo_event == 'long':
            controller.release_solo()

        received = controller.update(now_ms)
        if _bridge and _bridge.is_connected() and received:
            _bridge.forward(received)

        # A follower found a hotspot and alerted the leader — resume connecting
        # (even if we had given up), using the channel it reported to skip a scan.
        if received and controller.is_leader and received.get('type') == 'hotspot_found':
            _gave_up   = False
            _cap_fails = 0
            _retry_ms  = BRIDGE_RETRY_INIT_MS
            _retry_at  = now_ms
            _hint_ch   = received.get('ch')
            _log.write('main', 'hotspot alert received, resuming bridge')

        # Advance bridge state machine each tick — non-blocking (except the
        # one sanctioned scan inside start_connect at the moment of connecting).
        if controller.is_leader and not _gave_up:
            if _bridge is None:
                if time.ticks_diff(now_ms, _retry_at) >= 0:
                    from bridge import Bridge
                    _bridge = Bridge(mesh)
                    if _hint_ch is not None:
                        _bridge.set_channel_hint(_hint_ch)
                        _hint_ch = None
            else:
                result = _bridge.tick_connect(now_ms)
                if result is True:
                    _log.write('main', 'bridge connected')
                    _retry_ms  = BRIDGE_RETRY_INIT_MS
                    _cap_fails = 0
                    mesh.set_autonomous(False)
                    # Flush the local log buffer so the autonomous-lifecycle
                    # events that happened while disconnected reach the server.
                    for _e in _log.get_entries():
                        _bridge.forward({'type': 'log', 'sender': mesh.mac,
                                         'src': _e['src'], 'lvl': _e['lvl'],
                                         'msg': _e['msg']})
                elif result is False:
                    failed_interval = _retry_ms   # the interval that just failed
                    if failed_interval >= BRIDGE_RETRY_MAX_MS:
                        _cap_fails += 1   # already at the cap — count toward giving up
                    if failed_interval >= BRIDGE_AUTONOMOUS_AFTER_MS and not mesh.autonomous:
                        mesh.set_autonomous(True)  # 40s interval failed → autonomous
                        _log.write('main', 'no server yet, declaring autonomous', level='warn')
                    _retry_ms = min(_retry_ms * 2, BRIDGE_RETRY_MAX_MS)
                    _retry_at = time.ticks_add(now_ms, _retry_ms)
                    _bridge = None
                    if _cap_fails >= BRIDGE_CAP_RETRIES:
                        _gave_up = True
                        _log.write('main', 'no server found, stopped scanning', level='warn')

        # Tick bridge: forward mesh messages and execute incoming commands.
        # check_server_alive() resets to IDLE if heartbeats go silent.
        if _bridge and _bridge.is_connected():
            if not _bridge.check_server_alive(now_ms):
                _log.write('main', 'server heartbeat lost, reconnecting', level='warn')
                _bridge    = None
                _retry_ms  = BRIDGE_RETRY_INIT_MS
                _cap_fails = 0
                _retry_at  = time.ticks_add(now_ms, BRIDGE_RETRY_INIT_MS)
            else:
                cmd = _bridge.tick()
                if cmd:
                    _execute_bridge_command(cmd, controller, now_ms)

        # New-controller wake scan: a freshly-booted follower that sees the mesh
        # running autonomously does one boot scan and alerts the leader if it
        # finds a hotspot — re-waking a leader that had given up. One-shot.
        if (not controller.is_leader and not _wake_scanned
                and mesh.mesh_autonomous
                and time.ticks_diff(now_ms, _boot_ms) < WAKE_SCAN_WINDOW_MS):
            _wake_scanned = True
            from mesh import scan_channel
            from secrets import OTA_SSID as _SSID
            ch = scan_channel(_SSID)
            if ch is not None:
                mesh.send_hotspot_found(ch)
                _log.write('main', 'found hotspot while autonomous, alerting leader')

        # Orphan recovery (non-leaders only). If silent too long, rescan for the
        # hotspot and re-pin to its channel — handles a missed set_channel or a
        # hotspot that appeared after this controller had already migrated.
        if not controller.is_leader and mesh.silent_for(now_ms) > ORPHAN_SILENCE_MS:
            if time.ticks_diff(now_ms, _last_recovery_ms) > ORPHAN_SILENCE_MS:
                _last_recovery_ms = now_ms
                from mesh import scan_channel
                from secrets import OTA_SSID as _SSID
                ch = scan_channel(_SSID)
                if ch is not None:
                    mesh.apply_channel(ch)
                else:
                    mesh.apply_channel(DEFAULT_CHANNEL)
                mesh.announce()  # re-announce presence on the (possibly new) channel
                _log.write('main', 'orphan recovery rescan', level='warn')

        # Handle OTA update requested via mesh (non-leader controllers)
        if controller.ota_requested:
            _run_ota()


main()
