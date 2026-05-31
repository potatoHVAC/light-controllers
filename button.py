import time
from machine import Pin


class Button:
    """Debounced button with short press and long press detection.
    Wired active-low: GPIO -> button -> GND, internal pull-up enabled."""

    def __init__(self, pin_num, debounce_ms=30, long_press_ms=500):
        self._pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        self._debounce_ms = debounce_ms
        self._long_press_ms = long_press_ms
        self._last_raw = 1
        self._state = 1
        self._debounce_start = 0
        self._press_start = 0
        self._is_pressed = False
        self._long_fired = False

    def update(self, now_ms):
        """Call every loop tick. Returns 'short', 'long', or None."""
        raw = self._pin.value()
        if raw != self._last_raw:
            self._debounce_start = now_ms
        self._last_raw = raw

        if time.ticks_diff(now_ms, self._debounce_start) < self._debounce_ms:
            return None

        event = None

        if raw == 0 and self._state == 1:
            self._state = 0
            self._press_start = now_ms
            self._is_pressed = True
            self._long_fired = False
        elif raw == 1 and self._state == 0:
            self._state = 1
            if self._is_pressed and not self._long_fired:
                event = 'short'
            self._is_pressed = False

        if self._is_pressed and not self._long_fired:
            if time.ticks_diff(now_ms, self._press_start) >= self._long_press_ms:
                self._long_fired = True
                event = 'long'

        return event
