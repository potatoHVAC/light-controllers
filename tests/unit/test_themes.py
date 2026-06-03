from themes import ColorTheme, RandomTheme


def test_color_theme_name_and_color():
    t = ColorTheme((255, 0, 0), 'red')
    assert t.name == 'red'
    assert t.representative_color() == (255, 0, 0)


def test_color_theme_scenes_are_named_tuples():
    t = ColorTheme((0, 0, 255), 'blue')
    scenes = t.scenes()
    assert len(scenes) >= 1
    for name, scene in scenes:
        assert isinstance(name, str)
        assert hasattr(scene, 'update')   # it's a Scene


def test_random_theme_has_no_representative_color():
    t = RandomTheme()
    assert t.name == 'random'
    assert t.representative_color() is None


def test_random_theme_scene_instances_are_independent():
    # Each strip must get its own pattern instance (the firefly/rainbow fix).
    scenes = dict(RandomTheme().scenes())
    composed = scenes['firefly']
    pats = composed._patterns
    assert len(pats) >= 2
    assert pats[0] is not pats[1]
