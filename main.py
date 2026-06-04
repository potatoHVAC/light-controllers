import time
import os
from machine import Pin, WDT
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

# Strip data pins (up to 3). The number of LEDs on each comes from the
# per-controller device config; the default layout below is used when there is
# no config yet (the test rig: two short strips).
STRIP_PINS         = (26, 22, 21)
PRIMARY_PIN        = STRIP_PINS[0]
SECONDARY_PIN      = STRIP_PINS[1]
NUM_LEDS           = 3            # default per-strip length when unconfigured
BUTTON_PIN         = 33
BUTTON_SOLOIST_PIN = 27
_FW_VERSION_FILE   = 'firmware_version'

# Watchdog: resets the chip if the main loop stalls for this long (a hang, a
# wedged I/O call). Must exceed the longest in-loop blocking op — the ~2s WiFi
# scan — with margin. The OTA download is longer, so it feeds the watchdog itself.
WDT_TIMEOUT_MS   = 8000
# A persistent run of per-tick exceptions (bad state that won't clear) triggers a
# recovery reboot. A handful of transient errors are logged and shrugged off.
MAX_LOOP_ERRORS  = 50

# Failure indicator: kept small and dim so it reads as a fault, not a show cue,
# and never blasts a long strip at full power. First few LEDs at ~10% red.
ERROR_LEDS  = 3
ERROR_COLOR = (25, 0, 0)

# "Update in progress — do not power off" marker. Deliberately bright orange
# (unlike the dim red fault marker) so a person knows not to pull power during a
# flash-writing window (the A/B swap below, and OTA). Sized to DANGER_LEDS, which
# lights whatever LEDs are physically present — works on a 3-LED or a 1-LED strip.
DANGER_LEDS  = 3
DANGER_COLOR = (255, 80, 0)

_UPDATE_READY = '/update_ready'
_UPDATE_DIR   = '/update'


def _danger_on(leds=DANGER_LEDS):
    """Light the first few primary-strip LEDs full orange to signal a flash
    write is in progress and power must not be cut. Best-effort; never raises."""
    try:
        import neopixel
        np = neopixel.NeoPixel(Pin(PRIMARY_PIN), leds)
        for i in range(leds):
            np[i] = DANGER_COLOR
        np.write()
    except Exception:
        pass


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
    _danger_on()              # orange: writing flash, do not power off
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


def _strip_layout():
    """[(pin, num_leds), ...] for this controller — from device config, or the
    default test-rig layout when unconfigured."""
    import device_config
    strips = device_config.load().get('strips')
    if strips:
        return [(STRIP_PINS[i], n) for i, n in enumerate(strips[:len(STRIP_PINS)]) if n]
    return [(PRIMARY_PIN, NUM_LEDS), (SECONDARY_PIN, NUM_LEDS)]


def _blackout(layout):
    import neopixel
    for pin, leds in layout:
        np = neopixel.NeoPixel(Pin(pin), leds)
        np.fill((0, 0, 0))
        np.write()


def _primary(layout):
    """The primary strip's (pin, leds) for status/fault indicators."""
    return layout[0] if layout else (PRIMARY_PIN, NUM_LEDS)


def _run_ota(wdt=None):
    """Black out the strips, then download and stage an OTA update and reboot.

    The download blocks far longer than the watchdog timeout, so the watchdog's
    feed is threaded into the download loop to keep it alive during the update."""
    import neopixel
    import machine
    layout = _strip_layout()
    _blackout(layout)   # lights off before the update, not frozen on last frame
    pin, leds = _primary(layout)
    np = neopixel.NeoPixel(Pin(pin), leds)
    from ota import run as ota_run
    if ota_run(np=np, feed=(wdt.feed if wdt else None)):
        machine.reset()
    del np


def _error_flash_and_reset(reason):
    """Last resort: flash a small, dim red fault marker on the first few LEDs of
    the primary strip, then reset to recover. Used for fatal or persistent errors."""
    try:
        import neopixel
        pin, leds = _primary(_strip_layout())
        np = neopixel.NeoPixel(Pin(pin), leds)
        n = min(ERROR_LEDS, leds)
        for _ in range(3):
            np.fill((0, 0, 0))
            for i in range(n):
                np[i] = ERROR_COLOR
            np.write(); time.sleep_ms(150)
            np.fill((0, 0, 0)); np.write(); time.sleep_ms(150)
    except Exception:
        pass
    import machine
    machine.reset()


def _execute_bridge_command(cmd, ctrl, now_ms, wdt=None):
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
        ctrl.set_master_dim(dim)
        if ctrl._network:
            ctrl._network.send_dim(dim)
    elif cmd_type == 'solo':
        if cmd.get('active', False):
            ctrl.solo(cmd.get('dim'))
        else:
            ctrl.release_solo()
    elif cmd_type == 'ota_update':
        target = cmd.get('target')
        if ctrl._network:
            ctrl._network.send_ota_update()
        if target is None or (ctrl._network and target == ctrl._network.mac):
            _run_ota(wdt)
    elif cmd_type == 'identify':
        target = cmd.get('target')
        if ctrl._network:
            ctrl._network.send_identify(target)
        if target is None or (ctrl._network and target == ctrl._network.mac):
            ctrl.apply_identify(now_ms)
    elif cmd_type == 'solo_request':
        target = cmd.get('target')
        if ctrl._network:
            ctrl._network.send_solo_request(target, cmd.get('dim'))
        if target is None or (ctrl._network and target == ctrl._network.mac):
            ctrl.solo(cmd.get('dim'))
    elif cmd_type == 'solo_tag':
        active = cmd.get('active', True)
        if ctrl._network:
            ctrl._network.send_solo_tag(cmd.get('tag'), cmd.get('dim'), active)
        ctrl.apply_solo_tag(cmd.get('tag'), cmd.get('dim'), active, now_ms)
    elif cmd_type == 'default':
        if ctrl._network:
            ctrl._network.send_default()
        ctrl.apply_default(now_ms)
    elif cmd_type == 'set_config':
        target = cmd.get('target')
        if ctrl._network:
            ctrl._network.send_set_config(target, cmd.get('config'))
        if target is None or (ctrl._network and target == ctrl._network.mac):
            ctrl.apply_set_config(cmd.get('config'))


def _read_firmware_version():
    try:
        with open(_FW_VERSION_FILE) as f:
            return f.read().strip() or None
    except Exception:
        return None


def main():
    import device_config
    dev = device_config.load()

    layout = _strip_layout()
    names = ('primary', 'secondary', 'tertiary')
    strips = [Strip(names[i], pin, leds) for i, (pin, leds) in enumerate(layout)]
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
    mesh.set_versions(_read_firmware_version(), device_config.version(dev))
    _log.set_mesh(mesh)
    controller = Controller(fixture, themes, network=mesh, personal_default=dev)

    # Watchdog resets the chip if a tick stalls. Created here (after the A/B
    # swap and module setup, which run before main() and can't feed it) and fed
    # in both the sync spin and the main loop. The sync phase may legitimately
    # wait a long time, so it feeds the watchdog too — only a genuine hang resets.
    wdt = WDT(timeout=WDT_TIMEOUT_MS)

    # Sync/election phase. Non-blocking per tick; we spin here until it completes.
    controller.begin(time.ticks_ms())
    while not controller.tick_start(time.ticks_ms(), button.update(time.ticks_ms()) is not None):
        wdt.feed()

    link     = LeaderLink(mesh)
    recovery = FollowerRecovery(time.ticks_ms())
    if controller.is_leader:
        link.make_bridge()

    errors = 0

    while True:
        wdt.feed()
        try:
            now_ms = time.ticks_ms()

            _handle_buttons(controller, button, soloist_button, now_ms)

            received = controller.update(now_ms)
            link.forward(received)
            link.on_alert(controller, received, now_ms)

            cmd = link.tick(controller, now_ms)
            if cmd:
                _execute_bridge_command(cmd, controller, now_ms, wdt)

            recovery.tick(controller, mesh, now_ms)

            if controller.ota_requested:
                _run_ota(wdt)

            if controller.reboot_requested:
                import machine
                machine.reset()   # apply a freshly pushed config

            errors = 0
        except Exception as e:
            # One bad tick shouldn't drop the show: log and carry on. A
            # persistent run of errors means broken state — reboot to recover.
            errors += 1
            _log.write('main', 'loop error: ' + str(e), level='error')
            if errors >= MAX_LOOP_ERRORS:
                _error_flash_and_reset('persistent loop errors')


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


try:
    main()
except Exception as _e:
    # Fatal error (setup failure, or something that escaped the loop guard).
    # Flash red and reset rather than dropping to a dark REPL on stage.
    _error_flash_and_reset(str(_e))
