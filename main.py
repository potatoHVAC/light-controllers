import time
import os
from machine import Pin
from strip import Strip
from fixture import Fixture
from button import Button
from themes import RandomTheme, ColorTheme
from controller import Controller
from mesh import Mesh

# LED Brain: 2 strips × 3 LEDs
PRIMARY_PIN        = 26
SECONDARY_PIN      = 22
NUM_LEDS           = 3
BUTTON_PIN         = 33
BUTTON_SOLOIST_PIN = 27

_OTA_FLAG     = '_ota_done'
_UPDATE_READY = '/update_ready'
_UPDATE_DIR   = '/update'


def _copy_tree(src, dst):
    """Recursively copy src directory into dst. dst='' means filesystem root."""
    for name in os.listdir(src):
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
            with open(s, 'rb') as sf, open(d, 'wb') as df:
                while True:
                    chunk = sf.read(512)
                    if not chunk:
                        break
                    df.write(chunk)


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
    _copy_tree(_UPDATE_DIR, '')
    _rm_tree(_UPDATE_DIR)
    os.remove(_UPDATE_READY)  # removed LAST — if power cuts before this, swap retries next boot
    import machine as _m
    _m.reset()
except OSError:
    # No marker — if /update/ exists it's an incomplete download (power cut
    # mid-download). Clean it up so it doesn't consume flash space.
    try:
        _rm_tree(_UPDATE_DIR)
    except OSError:
        pass

# Skip the OTA check on the boot immediately after a successful update
# to avoid re-downloading the firmware we just applied.
_post_ota = False
try:
    os.remove(_OTA_FLAG)
    _post_ota = True
except OSError:
    pass

if not _post_ota:
    import neopixel
    import machine
    _np = neopixel.NeoPixel(Pin(PRIMARY_PIN), NUM_LEDS)
    from ota import run as _ota_run
    if _ota_run(np=_np):
        with open(_OTA_FLAG, 'w') as _f:
            _f.write('1')
        machine.reset()
    del _np


def main():
    strips = [
        Strip("primary",   PRIMARY_PIN,   NUM_LEDS),
        Strip("secondary", SECONDARY_PIN, NUM_LEDS),
    ]
    fixture = Fixture(strips)
    button        = Button(BUTTON_PIN)
    soloist_button = Button(BUTTON_SOLOIST_PIN)

    themes = [
        RandomTheme(),
        ColorTheme((255, 0, 0)),
        ColorTheme((0, 0, 255)),
    ]

    fixture.clear()

    mesh = Mesh()
    controller = Controller(fixture, themes, network=mesh)
    controller.start(time.ticks_ms(), button=button)

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
        controller.update(now_ms)


main()
