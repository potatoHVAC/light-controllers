from config import THEMES
from server import firmware
from server.api import Api, short_mac
from server.db import Database
from server.serverlog import ServerLog


class FakeLink:
    def __init__(self):
        self.sent = []
        self.mesh_state = {'theme': 'red', 'scene': 'solid', 'dim': 1.0,
                           'solo_active': False, 'leader': False, 'autonomous': False}
        self._online = {}

    def send_command(self, cmd, target=None):
        self.sent.append((dict(cmd), target))
        return True

    def connected(self):
        return True

    def online(self, timeout=20):
        return dict(self._online)


def _api(tmp_path):
    db = Database(':memory:')
    link = FakeLink()
    return Api(db, link, ServerLog(), tmp_path, THEMES), db, link


def test_short_mac():
    assert short_mac('001122334455') == '334455'


def test_next_scene_advances_within_theme(tmp_path):
    api, _, link = _api(tmp_path)            # red scenes: solid, breathe
    api.next_scene()
    cmd, target = link.sent[-1]
    assert cmd['type'] == 'change' and cmd['theme'] == 'red' and cmd['scene'] == 'breathe'


def test_next_theme_advances(tmp_path):
    api, _, link = _api(tmp_path)            # red -> blue
    api.next_theme()
    cmd, _ = link.sent[-1]
    assert cmd['theme'] == 'blue' and cmd['scene'] == 'solid'


def test_random_scene_keeps_theme_clears_scene(tmp_path):
    api, _, link = _api(tmp_path)
    api.random_scene()
    cmd, _ = link.sent[-1]
    assert cmd['theme'] == 'red' and cmd['scene'] is None


def test_solo_and_identify_are_targeted(tmp_path):
    api, _, link = _api(tmp_path)
    api.solo_controller('mac1', dim=0.25)
    cmd, target = link.sent[-1]
    assert cmd['type'] == 'solo_request' and cmd['dim'] == 0.25 and target == 'mac1'
    api.identify('mac2')
    assert link.sent[-1] == ({'type': 'identify'}, 'mac2')


def test_solo_tag_broadcasts(tmp_path):
    api, _, link = _api(tmp_path)
    api.solo_tag('horns', dim=0.3)
    cmd, target = link.sent[-1]
    assert cmd['type'] == 'solo_tag' and cmd['tag'] == 'horns'
    assert cmd['dim'] == 0.3 and target is None   # broadcast, not targeted


def test_default_user_and_show(tmp_path):
    api, db, link = _api(tmp_path)
    api.default_user()
    assert link.sent[-1][0]['type'] == 'default'
    db.update_defaults(unassigned_theme='blue', unassigned_scene='breathe')
    api.default_show()
    cmd, _ = link.sent[-1]
    assert cmd['theme'] == 'blue' and cmd['scene'] == 'breathe'


def test_save_config_persists_and_pushes(tmp_path):
    api, db, link = _api(tmp_path)
    api.save_config('mac1', {'nickname': 'Snare', 'strip1_leds': 30}, tags=['low'])
    assert db.get_controller('mac1')['nickname'] == 'Snare'
    assert db.controller_tags('mac1') == ['low']
    cmd, target = link.sent[-1]
    assert cmd['type'] == 'set_config' and target == 'mac1'
    assert cmd['config']['strips'][0] == 30


def test_deploy_outdated_targets_only_stale(tmp_path):
    api, _, link = _api(tmp_path)
    version = firmware.current_version(tmp_path)
    link._online = {
        'good': {'last_seen': 0, 'fw': version, 'cfg': None, 'theme': None,
                 'scene': None, 'dim': 1.0, 'leader': False},
        'old':  {'last_seen': 0, 'fw': 'stale00', 'cfg': None, 'theme': None,
                 'scene': None, 'dim': 1.0, 'leader': False},
    }
    result = api.deploy_outdated()
    assert result['targets'] == ['old']
    assert link.sent[-1] == ({'type': 'ota_update'}, 'old')


def test_deploy_all_configs_pushes_each_assigned(tmp_path):
    api, db, link = _api(tmp_path)
    db.upsert_controller('mac1', nickname='Snare')
    db.upsert_controller('mac2', nickname='Kick')
    result = api.deploy_all_configs()
    assert result['pushed'] == 2
    targets = {t for _, t in link.sent}
    assert targets == {'mac1', 'mac2'}
    types = {cmd['type'] for cmd, _ in link.sent}
    assert types == {'set_config'}


def test_deploy_all_configs_empty(tmp_path):
    api, _, link = _api(tmp_path)
    result = api.deploy_all_configs()
    assert result == {'pushed': 0}
    assert link.sent == []


def test_controllers_merges_registry_and_db(tmp_path):
    api, db, link = _api(tmp_path)
    db.upsert_controller('mac1', nickname='Snare')
    link._online = {'mac1': {'last_seen': 0, 'fw': 'x', 'cfg': 1, 'theme': 'red',
                             'scene': 'solid', 'dim': 1.0, 'leader': True},
                    'mac2': {'last_seen': 0, 'fw': 'x', 'cfg': None, 'theme': None,
                             'scene': None, 'dim': 1.0, 'leader': False}}
    rows = {c['mac']: c for c in api.controllers()}
    assert rows['mac1']['nickname'] == 'Snare' and rows['mac1']['assigned'] is True
    assert rows['mac2']['nickname'] == short_mac('mac2') and rows['mac2']['assigned'] is False
    assert rows['mac1']['online'] is True


def test_controllers_has_nickname_flag(tmp_path):
    api, db, link = _api(tmp_path)
    db.upsert_controller('mac1', nickname='Snare')
    db.upsert_controller('mac2')          # assigned but no nickname
    link._online = {}
    rows = {c['mac']: c for c in api.controllers()}
    assert rows['mac1']['has_nickname'] is True
    assert rows['mac2']['has_nickname'] is False


def test_controllers_sort_named_first_then_mac_order(tmp_path):
    api, db, link = _api(tmp_path)
    db.upsert_controller('mac3', nickname='Zebra')
    db.upsert_controller('mac1', nickname='Alpha')
    db.upsert_controller('mac2')          # unnamed
    link._online = {}
    result = api.controllers()
    nicknames = [c['nickname'] for c in result]
    # Named come first, alphabetically; unnamed (shown as short MAC) come after
    assert nicknames.index('Alpha') < nicknames.index('Zebra')
    assert nicknames.index('Zebra') < result.index(
        next(c for c in result if c['mac'] == 'mac2')
    )


# ── shows ─────────────────────────────────────────────────────────────────────

def test_save_show_creates_with_roster_and_tags(tmp_path):
    api, db, link = _api(tmp_path)
    show = api.save_show(None, {'name': 'Friday', 'default_theme': 'blue'},
                         controllers=['mac1', 'mac2'], tags=['outdoor'])
    assert show['name'] == 'Friday'
    assert show['controllers'] == ['mac1', 'mac2']
    assert show['tags'] == ['outdoor']


def test_save_show_updates_existing(tmp_path):
    api, db, link = _api(tmp_path)
    show = api.save_show(None, {'name': 'Gig', 'default_theme': 'red'})
    api.save_show(show['id'], {'name': 'Gig', 'default_theme': 'blue'})
    assert db.get_show(show['id'])['default_theme'] == 'blue'


def test_shows_lists_with_active_id(tmp_path):
    api, db, link = _api(tmp_path)
    s = api.save_show(None, {'name': 'Gig'})
    assert api.shows()['active_id'] is None
    api.activate_show(s['id'])
    out = api.shows()
    assert out['active_id'] == s['id']
    assert len(out['shows']) == 1


def test_activate_show_pushes_defaults_to_mesh(tmp_path):
    api, db, link = _api(tmp_path)
    s = api.save_show(None, {'name': 'Gig', 'default_theme': 'blue',
                             'default_scene': 'breathe', 'default_color': '#ff0000'})
    api.activate_show(s['id'])
    cmd, _ = link.sent[-1]
    assert cmd['type'] == 'change'
    assert cmd['theme'] == 'blue' and cmd['scene'] == 'breathe'
    assert cmd['color'] == [255, 0, 0]


def test_activate_show_without_theme_sends_nothing(tmp_path):
    api, db, link = _api(tmp_path)
    s = api.save_show(None, {'name': 'Empty'})
    before = len(link.sent)
    api.activate_show(s['id'])
    assert len(link.sent) == before        # no change command sent


def test_delete_show(tmp_path):
    api, db, link = _api(tmp_path)
    s = api.save_show(None, {'name': 'Gig'})
    api.delete_show(s['id'])
    assert db.get_show(s['id']) is None
