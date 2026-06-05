"""FollowerRecovery: orphan rescan when silent for too long.
BridgeRecovery tests are in test_bridge_recovery.py."""
import harness
from fakes.bus import BUS
from mesh import Mesh
from recovery import FollowerRecovery, ORPHAN_SILENCE_MS


class FakeController:
    is_leader = False


def test_orphan_rescan_repins_to_hotspot_channel():
    BUS.bind(0); mesh = Mesh()
    BUS.hotspots['TESTNET'] = 8           # secrets.OTA_SSID
    rec = FollowerRecovery(harness.now())

    harness.advance(ORPHAN_SILENCE_MS + 1000)
    BUS.bind(0)
    rec.tick(FakeController(), mesh, harness.now())

    assert BUS.node(0).channel == 8       # re-pinned to hotspot channel


def test_orphan_rescan_not_triggered_before_silence():
    BUS.bind(0); mesh = Mesh()
    BUS.hotspots['TESTNET'] = 8
    rec = FollowerRecovery(harness.now())

    harness.advance(ORPHAN_SILENCE_MS - 1000)
    # Keep mesh alive so silence timer doesn't trip
    BUS.bind(0)
    rec.tick(FakeController(), mesh, harness.now())

    assert BUS.node(0).channel == 1      # unchanged, default channel