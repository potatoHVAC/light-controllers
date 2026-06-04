"""Fake machine module: Pin, PWM, reset."""


class Pin:
    IN        = 0
    OUT       = 1
    PULL_UP   = 2
    PULL_DOWN = 3

    def __init__(self, id, mode=-1, pull=-1):
        self.id = id
        # Active-low buttons idle high with the internal pull-up.
        self._value = 1

    def value(self, v=None):
        if v is None:
            return self._value
        self._value = v


class PWM:
    def __init__(self, pin, freq=1000):
        self._duty = 0

    def duty(self, d=None):
        if d is None:
            return self._duty
        self._duty = d


class WDT:
    def __init__(self, timeout=5000):
        self.timeout = timeout
        self.feeds = 0

    def feed(self):
        self.feeds += 1


def reset():
    raise SystemExit('machine.reset')


# Reset-cause constants mirror the ESP32 port. boot.py uses these to tell a user
# power-on from a firmware fault.
PWRON_RESET     = 1
HARD_RESET      = 2
WDT_RESET       = 3
DEEPSLEEP_RESET = 4
SOFT_RESET      = 5

_reset_cause = PWRON_RESET


def reset_cause():
    return _reset_cause
