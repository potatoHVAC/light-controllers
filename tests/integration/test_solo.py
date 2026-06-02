"""Solo: the soloist stays full, everyone else dims; release restores all."""
import harness
from harness import Simulation
from fakes.bus import BUS


def _synced(n):
    sim = Simulation(n)
    assert sim.boot_one(0)
    assert sim.start_followers(0)
    return sim


def test_solo_dims_others_keeps_soloist_full():
    sim = _synced(2)
    leader, soloist = sim.nodes[0], sim.nodes[1]

    BUS.bind(1)
    soloist.ctrl.solo()
    sim.run(1000)

    assert soloist.ctrl.status()['dim'] == 1.0
    assert leader.ctrl.status()['dim'] < 1.0


def test_release_solo_restores_full_brightness():
    sim = _synced(2)
    leader, soloist = sim.nodes[0], sim.nodes[1]

    BUS.bind(1)
    soloist.ctrl.solo()
    sim.run(1000)
    assert leader.ctrl.status()['dim'] < 1.0

    BUS.bind(1)
    soloist.ctrl.release_solo()
    sim.run(2000)   # release fades back to full over ~1s
    assert leader.ctrl.status()['dim'] == 1.0


def test_new_soloist_takes_over_from_previous():
    sim = _synced(3)
    a, b, c = sim.nodes

    BUS.bind(1)
    b.ctrl.solo()
    sim.run(1000)
    assert b.ctrl.status()['dim'] == 1.0
    assert c.ctrl.status()['dim'] < 1.0

    BUS.bind(2)
    c.ctrl.solo()
    sim.run(1000)
    # c is now the soloist (full); the previous soloist b drops to dim.
    assert c.ctrl.status()['dim'] == 1.0
    assert b.ctrl.status()['dim'] < 1.0
