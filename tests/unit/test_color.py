import color


def test_scale_halves_each_channel():
    assert color.scale((200, 100, 50), 0.5) == (100, 50, 25)


def test_scale_zero_is_black():
    assert color.scale((255, 255, 255), 0.0) == (0, 0, 0)


def test_color_max_per_channel():
    assert color.color_max((10, 200, 30), (50, 100, 30)) == (50, 200, 30)


def test_exp_falloff_is_one_at_head_and_decays():
    assert abs(color.exp_falloff(0) - 1.0) < 1e-9
    assert color.exp_falloff(1) < 1.0
    assert color.exp_falloff(5) < color.exp_falloff(1)


def test_hsv_saturation_zero_is_grey():
    assert color.hsv_to_rgb(123, 0, 200) == (200, 200, 200)


def test_hsv_outputs_stay_in_gamut():
    for h in range(0, 256, 7):
        r, g, b = color.hsv_to_rgb(h, 255, 255)
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255


def test_hsv_full_value_has_a_max_channel():
    # A fully saturated, full-value color should peak at 255 somewhere.
    for h in range(0, 256, 11):
        assert max(color.hsv_to_rgb(h, 255, 255)) == 255
