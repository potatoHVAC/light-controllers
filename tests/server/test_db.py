from server.db import Database


def _db():
    return Database(':memory:')


def test_upsert_creates_and_bumps_version():
    db = _db()
    c1 = db.upsert_controller('aa:bb', nickname='Snare', strip1_leds=30)
    assert c1['nickname'] == 'Snare' and c1['strip1_leds'] == 30
    assert c1['config_version'] == 1
    c2 = db.upsert_controller('aa:bb', strip1_leds=40)
    assert c2['strip1_leds'] == 40 and c2['config_version'] == 2  # bumped


def test_ignores_unknown_fields():
    db = _db()
    c = db.upsert_controller('aa:bb', nickname='X', bogus='nope')
    assert 'bogus' not in c


def test_tags_are_agnostic_and_queryable():
    db = _db()
    db.upsert_controller('m1', nickname='A')
    db.upsert_controller('m2', nickname='B')
    db.set_tags('m1', ['percussion', 'low'])
    db.set_tags('m2', ['percussion'])
    assert db.controller_tags('m1') == ['low', 'percussion']
    assert sorted(db.macs_with_tag('percussion')) == ['m1', 'm2']
    assert db.macs_with_tag('low') == ['m1']


def test_set_tags_replaces():
    db = _db()
    db.upsert_controller('m1')
    db.set_tags('m1', ['a', 'b'])
    db.set_tags('m1', ['c'])
    assert db.controller_tags('m1') == ['c']


def test_delete_controller_removes_tags():
    db = _db()
    db.upsert_controller('m1')
    db.set_tags('m1', ['a'])
    db.delete_controller('m1')
    assert db.get_controller('m1') is None
    assert db.macs_with_tag('a') == []


def test_defaults_singleton_update():
    db = _db()
    assert db.get_defaults()['show_theme'] is None
    d = db.update_defaults(show_theme='red', show_scene='solid', unassigned_strip1_leds=12)
    assert d['show_theme'] == 'red' and d['unassigned_strip1_leds'] == 12
    # still a single row
    assert db.get_defaults()['show_scene'] == 'solid'


def test_list_controllers_sorted():
    db = _db()
    db.upsert_controller('m2', nickname='Zed')
    db.upsert_controller('m1', nickname='Abe')
    names = [c['nickname'] for c in db.list_controllers()]
    assert names == ['Abe', 'Zed']
