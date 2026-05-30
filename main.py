import time
from strip import Strip
from fixture import Fixture
from button import Button
from themes import RandomTheme, ColorTheme
from controller import Controller
from mesh import Mesh

# LED Brain: 2 strips × 3 LEDs
PRIMARY_PIN   = 26
SECONDARY_PIN = 22
NUM_LEDS      = 3
BUTTON_PIN    = 33


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
