"""Targeted control messages: identify, solo_request, set_config, default — and
the target filtering that scopes them to one controller."""
import json

import harness
import device_config
from fakes.bus import BUS
from strip import Strip
from fixture import Fixture
from mesh import Mesh
from controller import Controller
from themes import RandomTheme, ColorTheme


def _controller(nid=0, personal_default=None):
    BUS.bind(nid)
    fx = Fixture([Strip('p', 26, 3), Strip('s', 22, 3)])
    mesh = Mesh()
    ctrl = Controller(fx, [RandomTheme(), ColorTheme((255, 0, 0), 'red')],
                      network=mesh, personal_default=personal_default)
    return ctrl, mesh


def _inject(nid, packet):
    BUS.node(nid).inbox.append(('x', json.dumps(packet)))


def test_targeted_filtering():
    ctrl, mesh = _controller()
    assert ctrl._targeted({'target': None})
    assert ctrl._targeted({'target': mesh.mac})
    assert not ctrl._targeted({'target': 'somebody-else'})


def test_identify_message_sets_window():
    ctrl, mesh = _controller()
    _inject(0, {'type': 'identify', 'sender': 'srv', 'seq': 1, 'target': mesh.mac})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._identify_until_ms is not None


def test_identify_ignored_when_not_targeted():
    ctrl, mesh = _controller()
    _inject(0, {'type': 'identify', 'sender': 'srv', 'seq': 1, 'target': 'other'})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._identify_until_ms is None


def test_solo_request_triggers_solo():
    ctrl, mesh = _controller()
    _inject(0, {'type': 'solo_request', 'sender': 'srv', 'seq': 1, 'target': mesh.mac})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._is_soloist is True


def test_set_config_saves_and_requests_reboot():
    ctrl, mesh = _controller()
    cfg = {'nickname': 'Snare', 'strips': [30, 0, 0], 'version': 4}
    _inject(0, {'type': 'set_config', 'sender': 'srv', 'seq': 1,
                'target': mesh.mac, 'config': cfg})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl.reboot_requested is True
    assert device_config.load()['nickname'] == 'Snare'


def test_default_applies_personal_default():
    ctrl, mesh = _controller(personal_default={'default_theme': 'red',
                                               'default_scene': 'breathe'})
    _inject(0, {'type': 'default', 'sender': 'srv', 'seq': 1})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl.status()['theme'] == 'red'
    assert ctrl.status()['scene'] == 'breathe'


def test_solo_respects_master_dim():
    """Soloing sits at the master level, not full brightness."""
    ctrl, mesh = _controller()
    ctrl.set_master_dim(0.5)
    ctrl.solo()
    assert ctrl.status()['dim'] == 0.5


def test_solo_message_dims_non_soloist_to_target():
    ctrl, mesh = _controller()
    _inject(0, {'type': 'solo', 'sender': 'other', 'seq': 1, 'active': True, 'dim': 0.3})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._is_soloist is False
    assert ctrl.status()['dim'] == 0.3


def test_solo_tag_matching_controller_solos():
    ctrl, mesh = _controller(personal_default={'tags': ['horns']})
    _inject(0, {'type': 'solo_tag', 'sender': 'srv', 'seq': 1,
                'tag': 'horns', 'dim': 0.2, 'active': True})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._is_soloist is True
    assert ctrl.status()['dim'] == 1.0          # master default, full


def test_solo_tag_non_matching_controller_dims():
    ctrl, mesh = _controller(personal_default={'tags': ['drums']})
    _inject(0, {'type': 'solo_tag', 'sender': 'srv', 'seq': 1,
                'tag': 'horns', 'dim': 0.2, 'active': True})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._is_soloist is False
    assert ctrl.status()['dim'] == 0.2          # master(1.0) * 0.2


def test_solo_tag_release_fades_back():
    ctrl, mesh = _controller(personal_default={'tags': ['drums']})
    _inject(0, {'type': 'solo_tag', 'sender': 'srv', 'seq': 1,
                'tag': 'horns', 'dim': 0.2, 'active': True})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._solo_active is True
    _inject(0, {'type': 'solo_tag', 'sender': 'srv', 'seq': 2,
                'tag': 'horns', 'active': False})
    BUS.bind(0)
    ctrl.update(harness.now())
    assert ctrl._solo_active is False
