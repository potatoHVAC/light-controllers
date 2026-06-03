"""Bridge: signed-command verification/dedup, and the scan→announce→associate
connect flow (channel announced to the mesh before associating)."""
import json
import types

import auth
import harness
from secrets import BRIDGE_SECRET
from config import DISCOVERY_MSG
from fakes.bus import BUS
from mesh import Mesh
import bridge as bridge_mod
from bridge import Bridge


# ── fake UDP socket ───────────────────────────────────────────────────────────

class FakeUDP:
    def __init__(self):
        self.incoming = []
        self.sent     = []

    def feed(self, data, addr=('192.168.4.1', 5001)):
        self.incoming.append((data, addr))

    def setblocking(self, v): pass
    def bind(self, a): pass
    def close(self): pass

    def recvfrom(self, n):
        if self.incoming:
            return self.incoming.pop(0)
        raise OSError('empty')

    def sendto(self, data, addr):
        self.sent.append((data, addr))


def _fake_socket_module():
    m = types.ModuleType('socket')
    m.AF_INET        = 2
    m.SOCK_DGRAM     = 2
    m.SOL_SOCKET     = 1
    m.SO_REUSEADDR   = 4
    m.socket         = lambda *a, **k: FakeUDP()
    return m


def _signed(cmd):
    payload = json.dumps(cmd, separators=(',', ':')).encode()
    sig = auth.sign(BRIDGE_SECRET, payload)
    return payload + b'|' + sig.encode()


def _bridge_with_sock():
    b = Bridge(mesh=object())
    b._sock = FakeUDP()
    b._laptop_ip = '192.168.4.1'
    return b


# ── command verification / dedup ──────────────────────────────────────────────

def test_valid_command_returned_and_acked():
    b = _bridge_with_sock()
    b._sock.feed(_signed({'seq': 1, 'type': 'dim', 'dim': 0.5}))
    cmd = b.tick()
    assert cmd and cmd['type'] == 'dim'
    assert any(b'ack' in s[0] for s in b._sock.sent)


def test_unsigned_command_rejected():
    b = _bridge_with_sock()
    b._sock.feed(b'{"seq":1,"type":"dim"}')   # no |sig
    assert b.tick() is None


def test_tampered_command_rejected():
    b = _bridge_with_sock()
    payload = json.dumps({'seq': 1, 'type': 'dim'}, separators=(',', ':')).encode()
    b._sock.feed(payload + b'|' + (b'0' * 64))
    assert b.tick() is None


def test_duplicate_seq_ignored():
    b = _bridge_with_sock()
    b._sock.feed(_signed({'seq': 5, 'type': 'next_scene'}))
    b._sock.feed(_signed({'seq': 5, 'type': 'next_scene'}))
    assert b.tick() is not None
    assert b.tick() is None


def test_server_heartbeat_updates_liveness_not_command():
    b = _bridge_with_sock()
    b._sock.feed(_signed({'seq': 2, 'type': 'server_heartbeat'}))
    assert b.tick() is None
    assert b._last_server_hb_ms is not None


# ── connect flow ──────────────────────────────────────────────────────────────

def test_connect_announces_channel_then_associates(monkeypatch):
    monkeypatch.setattr(bridge_mod, 'socket', _fake_socket_module())
    BUS.bind(0)
    mesh = Mesh()
    b = Bridge(mesh)
    BUS.hotspots['TESTNET'] = 6     # secrets.OTA_SSID == 'TESTNET'

    BUS.bind(0)
    assert b.tick_connect(harness.now()) is None      # IDLE -> scan/announce/associate
    assert BUS.node(0).channel == 6                    # mesh migrated to hotspot channel

    BUS.bind(0)
    assert b.tick_connect(harness.now()) is None       # CONNECTING -> DISCOVERING

    b._disc_sock.feed(DISCOVERY_MSG, ('192.168.4.1', 5000))
    BUS.bind(0)
    assert b.tick_connect(harness.now()) is True        # DISCOVERING -> CONNECTED
    assert b.is_connected()


def test_connect_fails_when_no_hotspot(monkeypatch):
    monkeypatch.setattr(bridge_mod, 'socket', _fake_socket_module())
    BUS.bind(0)
    mesh = Mesh()
    b = Bridge(mesh)
    # No hotspot registered → scan finds nothing → attempt fails.
    BUS.bind(0)
    assert b.tick_connect(harness.now()) is False
