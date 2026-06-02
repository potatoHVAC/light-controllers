"""Sequence-number dedup: a receiver accepts strictly-newer packets and drops
duplicates and stale ones, per sender."""
import json

import harness
from fakes.bus import BUS
from mesh import Mesh


def _inject(nid, packet):
    BUS.node(nid).inbox.append((0, json.dumps(packet)))


def test_accepts_newer_drops_duplicate_and_stale():
    BUS.bind(0); a = Mesh()
    BUS.bind(1); b = Mesh()
    src = a._mac

    def change(seq):
        return {'type': 'change', 'sender': src, 'seq': seq,
                'theme': 'red', 'scene': 'solid', 'dim': 1.0}

    _inject(1, change(5))   # new   -> accept
    _inject(1, change(5))   # dup   -> drop
    _inject(1, change(4))   # stale -> drop
    _inject(1, change(6))   # newer -> accept

    BUS.bind(1)
    now = harness.now()
    results = [b.tick('random', 'rainbow', 1.0, now) for _ in range(4)]

    assert results[0] and results[0]['seq'] == 5
    assert results[1] is None
    assert results[2] is None
    assert results[3] and results[3]['seq'] == 6


def test_ignores_own_mac():
    BUS.bind(0); a = Mesh()
    # A packet claiming to be from A's own mac must be ignored by A.
    _inject(0, {'type': 'change', 'sender': a._mac, 'seq': 99,
                'theme': 'red', 'scene': 'solid', 'dim': 1.0})
    BUS.bind(0)
    assert a.tick('red', 'solid', 1.0, harness.now()) is None
