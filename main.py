import time
from machine import Pin
from light_rig import LightRig
from network import Network

BTN_PIN = 25
DEBOUNCE_MS = 50
LOOP_MS = 10


def main():
    rig = LightRig(gpio=16)
    net = Network()
    btn = Pin(BTN_PIN, Pin.IN, Pin.PULL_UP)

    last_btn = 1
    last_press_ms = 0

    while True:
        now = time.ticks_ms()

        reading = btn.value()
        if reading == 0 and last_btn == 1:
            if time.ticks_diff(now, last_press_ms) > DEBOUNCE_MS:
                rig.next_pattern()
                net.broadcast_pattern(rig.pattern_index)
                last_press_ms = now
        last_btn = reading

        msg = net.receive()
        if msg and 'pattern' in msg:
            rig.set_pattern(msg['pattern'])

        rig.update(now)
        time.sleep_ms(LOOP_MS)


main()
