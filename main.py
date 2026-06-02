import time
import os
from machine import Pin
from strip import Strip
from fixture import Fixture
from button import Button
from themes import RandomTheme, ColorTheme
from config import THEMES as _THEME_DEFS
from controller import Controller
from mesh import Mesh
from leader_link import LeaderLink
from recovery import FollowerRecovery
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

    # Sync/election phase. Non-blocking per tick, but we spin here until it
    # completes — this runs before the main loop, so a tight loop is fine.
    controller.begin(time.ticks_ms())
    while not controller.tick_start(time.ticks_ms(), button.update(time.ticks_ms()) is not None):
        pass

    link     = LeaderLink(mesh)
    recovery = FollowerRecovery(time.ticks_ms())
    if controller.is_leader:
        link.make_bridge()

    while True:
        now_ms = time.ticks_ms()

        _handle_buttons(controller, button, soloist_button, now_ms)

        received = controller.update(now_ms)
        link.forward(received)
        link.on_alert(controller, received, now_ms)

        cmd = link.tick(controller, now_ms)
        if cmd:
            _execute_bridge_command(cmd, controller, now_ms)

        recovery.tick(controller, mesh, now_ms)

        if controller.ota_requested:
            _run_ota()


def _handle_buttons(controller, button, soloist_button, now_ms):
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


main()
