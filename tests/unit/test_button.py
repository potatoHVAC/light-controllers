"""Debounced button: short press on release, long press while held."""
from button import Button


def _press(btn):
    btn._pin.value(0)   # active-low: pressed = 0


def _release(btn):
    btn._pin.value(1)


def test_short_press_fires_on_release():
    b = Button(33, debounce_ms=30, long_press_ms=500)
    assert b.update(0) is None
    _press(b)
    assert b.update(100) is None      # debounce window starts
    assert b.update(140) is None      # press registered, no event yet
    _release(b)
    assert b.update(200) is None      # debounce window starts
    assert b.update(240) == 'short'   # release -> short press


def test_long_press_fires_while_held():
    b = Button(33, debounce_ms=30, long_press_ms=500)
    b.update(0)
    _press(b)
    b.update(100)
    b.update(140)                     # press registered at 140
    assert b.update(640) == 'long'    # held >= 500ms


def test_long_press_does_not_also_fire_short_on_release():
    b = Button(33, debounce_ms=30, long_press_ms=500)
    b.update(0)
    _press(b)
    b.update(100)
    b.update(140)
    assert b.update(640) == 'long'
    _release(b)
    b.update(700)
    assert b.update(740) is None      # long already fired; no short on release


def test_noise_shorter_than_debounce_is_ignored():
    b = Button(33, debounce_ms=30, long_press_ms=500)
    b.update(0)
    _press(b)
    b.update(100)                     # starts debounce
    _release(b)                       # bounced back before 30ms
    b.update(110)
    assert b.update(120) is None
