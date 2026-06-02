"""Channel migration: the leader announces the new channel on the current
channel (so followers move first), then switches. The mesh stays connected."""
import harness
from fakes.bus import BUS
from mesh import Mesh


def test_follower_migrates_then_mesh_reconnects():
    BUS.bind(0); a = Mesh()
    BUS.bind(1); b = Mesh()
    assert BUS.node(1).channel == 1

    # Leader announces ch6 (sent on ch1, where B still is), then moves itself.
    BUS.bind(0)
    a.announce_channel(6)
    a.apply_channel(6)
    assert BUS.node(0).channel == 6

    # B drains the set_channel burst and migrates.
    BUS.bind(1)
    for _ in range(6):
        b.tick('random', 'rainbow', 1.0, harness.now())
    assert BUS.node(1).channel == 6

    # Connectivity restored on ch6: A's heartbeat now reaches B.
    BUS.bind(0)
    a.tick('red', 'solid', 1.0, harness.now())   # emits a heartbeat on ch6
    BUS.bind(1)
    got = None
    for _ in range(3):
        m = b.tick('random', 'rainbow', 1.0, harness.now())
        if m:
            got = m
    assert got is not None and got.get('type') == 'heartbeat'


def test_apply_channel_is_noop_when_same():
    BUS.bind(0); a = Mesh()
    before = BUS.node(0).channel
    a.apply_channel(before)
    assert BUS.node(0).channel == before
