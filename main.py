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

_OTA_FLAG = '_ota_done'

# On every boot, check for an OTA server and update if one is found.
# Skip the check on the boot immediately following a successful update
# (flag file prevents an infinite update loop).
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
    button  = Button(BUTTON_PIN)

    themes = [
        RandomTheme(),
        ColorTheme((255, 0, 0)),
        ColorTheme((0, 0, 255)),
    ]

    fixture.clear()

    mesh = Mesh()
    controller = Controller(fixture, themes, network=mesh)

    # Stay dark until synced from network or manually started via button press.
    # Never fall back to saved state automatically — unexpected state mid-show
    # is worse than a delay.
    while True:
        now_ms = time.ticks_ms()
        if button.update(now_ms):
            break
        sync = mesh.check_sync()
        if sync:
            controller.apply_state(sync[0], sync[1], now_ms)
            break

    controller.start(time.ticks_ms())

    while True:
        now_ms = time.ticks_ms()
        event  = button.update(now_ms)
        if event == 'short':
            controller.next_scene(now_ms)
        elif event == 'long':
            controller.next_theme(now_ms)
        controller.update(now_ms)


main()
