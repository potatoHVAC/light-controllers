"""FollowerRecovery: orphan rescan when silent, and the one-shot wake scan that
alerts the leader when booted into an autonomous mesh."""
import json

import harness
from fakes.bus import BUS
from mesh import Mesh
from recovery import FollowerRecovery, ORPHAN_SILENCE_MS, WAKE_SCAN_WINDOW_MS


class FakeController:
    is_leader = False


def test_orphan_rescan_repins_to_hotspot_channel():
    BUS.bind(0); mesh = Mesh()
    BUS.hotspots['TESTNET'] = 8           # secrets.OTA_SSID
    rec = FollowerRecovery(harness.now())

    # Go silent past the threshold without receiving anything.
    harness.advance(ORPHAN_SILENCE_MS + 1000)
    BUS.bind(0)
    rec.tick(FakeController(), mesh, harness.now())

    assert BUS.node(0).channel == 8       # re-pinned to the hotspot channel


def test_wake_scan_alerts_leader_when_autonomous():
    BUS.bind(0); mesh = Mesh()
    BUS.bind(1); observer = Mesh()        # stands in for the leader, same channel
    BUS.hotspots['TESTNET'] = 6
    mesh._mesh_autonomous = True          # observed: leader is autonomous
    rec = FollowerRecovery(harness.now())

    BUS.bind(0)
    rec.tick(FakeController(), mesh, harness.now())

    # The observer should receive a hotspot_found alert naming the channel.
    found = None
    for _, raw in list(BUS.node(1).inbox):
        d = json.loads(raw)
        if d.get('type') == 'hotspot_found':
            found = d
    assert found is not None and found['ch'] == 6


def test_wake_scan_is_one_shot_and_window_bounded():
    BUS.bind(0); mesh = Mesh()
    BUS.hotspots['TESTNET'] = 6
    mesh._mesh_autonomous = True
    rec = FollowerRecovery(harness.now())

    # Past the boot window: no wake scan, so no alert is produced.
    harness.advance(WAKE_SCAN_WINDOW_MS + 1000)
    BUS.bind(0)
    rec.tick(FakeController(), mesh, harness.now())
    assert all(json.loads(raw).get('type') != 'hotspot_found'
               for _, raw in list(BUS.node(0).inbox))
