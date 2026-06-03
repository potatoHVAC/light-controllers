import time

from server.link import BridgeLink
from server.serverlog import ServerLog


def _link():
    return BridgeLink('secret', 5001, 5000, b'LIGHTRIG', ServerLog())


def _fwd(**fields):
    fields['fwd'] = True
    return fields


def test_heartbeat_updates_registry_and_state():
    link = _link()
    link.handle_packet(_fwd(type='heartbeat', sender='aa', theme='red', scene='solid',
                            dim=0.5, leader=True, fw='abc', cfg=2), ('1.2.3.4', 5001))
    assert link.mesh_state['theme'] == 'red'
    assert link.mesh_state['dim'] == 0.5
    assert link.mesh_state['leader'] is True
    info = link.registry['aa']
    assert info['fw'] == 'abc' and info['cfg'] == 2 and info['leader'] is True
    assert link.connected() is True


def test_solo_state_tracked():
    link = _link()
    link.handle_packet(_fwd(type='solo', sender='aa', active=True, dim=0.2), ('1.2.3.4', 5001))
    assert link.mesh_state['solo_active'] is True
    assert link.mesh_state['dim'] == 0.2


def test_non_forwarded_ignored():
    link = _link()
    link.handle_packet({'type': 'heartbeat', 'sender': 'aa'}, ('1.2.3.4', 5001))  # no fwd
    assert 'aa' not in link.registry


def test_online_prunes_stale():
    link = _link()
    link.handle_packet(_fwd(type='heartbeat', sender='aa'), ('1.2.3.4', 5001))
    link.registry['old'] = {'last_seen': time.time() - 999, 'fw': None, 'cfg': None,
                            'theme': None, 'scene': None, 'dim': 1.0, 'leader': False}
    online = link.online()
    assert 'aa' in online and 'old' not in online


def test_send_command_without_bridge_returns_false():
    link = _link()
    assert link.send_command({'type': 'dim', 'dim': 0.5}) is False
