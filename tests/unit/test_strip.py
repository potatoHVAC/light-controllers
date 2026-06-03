"""Strip dim scaling must apply once at show() time and never compound across
ticks — the bug that made dimmed random patterns pulse."""
from strip import Strip


def test_full_brightness_writes_unscaled():
    s = Strip('s', 26, 3)
    s.fill((200, 100, 50))
    s.show()
    assert s._np.written == [(200, 100, 50)] * 3


def test_dim_scales_at_show():
    s = Strip('s', 26, 3)
    s.dim = 0.5
    s.fill((200, 100, 50))
    s.show()
    assert s._np.written == [(100, 50, 25)] * 3


def test_dim_does_not_compound_across_repeated_shows():
    s = Strip('s', 26, 3)
    s.dim = 0.5
    s.fill((200, 200, 200))
    s.show()
    s.show()
    s.show()
    # Still 100, not 50 or 25 — the unscaled buffer is the source each time.
    assert s._np.written == [(100, 100, 100)] * 3


def test_dim_is_clamped():
    s = Strip('s', 26, 3)
    s.dim = 5.0
    assert s.dim == 1.0
    s.dim = -1.0
    assert s.dim == 0.0
