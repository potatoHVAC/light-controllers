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


# ── shows ─────────────────────────────────────────────────────────────────────

def test_create_and_get_show():
    db = _db()
    s = db.create_show('Friday Gig', default_theme='blue', default_scene='breathe')
    assert s['name'] == 'Friday Gig'
    assert s['default_theme'] == 'blue'
    assert s['controllers'] == [] and s['tags'] == []
    assert db.get_show(s['id'])['name'] == 'Friday Gig'


def test_list_shows_sorted_by_name():
    db = _db()
    db.create_show('Zed Show')
    db.create_show('Alpha Show')
    assert [s['name'] for s in db.list_shows()] == ['Alpha Show', 'Zed Show']


def test_update_show():
    db = _db()
    s = db.create_show('Gig', default_theme='red')
    db.update_show(s['id'], default_theme='blue', name='Gig 2')
    s2 = db.get_show(s['id'])
    assert s2['name'] == 'Gig 2' and s2['default_theme'] == 'blue'


def test_show_roster_and_multi_show_membership():
    db = _db()
    a = db.create_show('A')
    b = db.create_show('B')
    db.set_show_controllers(a['id'], ['mac1', 'mac2'])
    db.set_show_controllers(b['id'], ['mac1'])          # mac1 in both shows
    assert db.show_controllers(a['id']) == ['mac1', 'mac2']
    assert db.show_controllers(b['id']) == ['mac1']
    assert sorted(db.shows_for_controller('mac1')) == sorted([a['id'], b['id']])
    assert db.shows_for_controller('mac2') == [a['id']]


def test_add_show_controller_idempotent():
    db = _db()
    s = db.create_show('A')
    db.add_show_controller(s['id'], 'mac1')
    db.add_show_controller(s['id'], 'mac1')             # dupe ignored
    assert db.show_controllers(s['id']) == ['mac1']


def test_active_show_select_and_clear_on_delete():
    db = _db()
    s = db.create_show('Gig')
    assert db.get_active_show() is None
    db.set_active_show(s['id'])
    assert db.get_active_show()['id'] == s['id']
    db.delete_show(s['id'])
    assert db.get_active_show() is None                 # cleared when the show is deleted


def test_delete_show_removes_roster_and_tags():
    db = _db()
    s = db.create_show('Gig')
    db.set_show_controllers(s['id'], ['mac1'])
    db.set_show_tags(s['id'], ['outdoor'])
    db.delete_show(s['id'])
    assert db.get_show(s['id']) is None
    assert db.show_controllers(s['id']) == []


def test_show_tags():
    db = _db()
    s = db.create_show('Gig')
    db.set_show_tags(s['id'], ['outdoor', 'acoustic'])
    assert db.get_show(s['id'])['tags'] == ['acoustic', 'outdoor']
