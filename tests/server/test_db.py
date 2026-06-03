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


def test_has_custom_nickname_flag():
    db = _db()
    # Set when nickname is provided
    c = db.upsert_controller('m1', nickname='Snare')
    assert c['has_custom_nickname'] == 1
    # Clear when nickname is removed
    c = db.upsert_controller('m1', nickname=None)
    assert c['has_custom_nickname'] == 0
    # Not set if nickname is never provided
    c = db.upsert_controller('m2', strip1_leds=30)
    assert c['has_custom_nickname'] == 0


def test_migration_backfills_existing_nicknames():
    """Existing rows with nicknames must get has_custom_nickname=1 on first open."""
    import sqlite3, tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    try:
        # Simulate old DB without has_custom_nickname column
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE controllers (
            mac TEXT PRIMARY KEY, nickname TEXT,
            strip1_leds INTEGER NOT NULL DEFAULT 0,
            strip2_leds INTEGER NOT NULL DEFAULT 0,
            strip3_leds INTEGER NOT NULL DEFAULT 0,
            default_theme TEXT, default_scene TEXT, default_color TEXT,
            config_version INTEGER NOT NULL DEFAULT 1,
            updated_at REAL NOT NULL DEFAULT 0)""")
        conn.execute("INSERT INTO controllers (mac, nickname) VALUES ('m1', 'Snare')")
        conn.execute("INSERT INTO controllers (mac, nickname) VALUES ('m2', NULL)")
        conn.commit()
        conn.close()

        db = Database(path)
        assert db.get_controller('m1')['has_custom_nickname'] == 1
        assert db.get_controller('m2')['has_custom_nickname'] == 0
    finally:
        os.unlink(path)


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
