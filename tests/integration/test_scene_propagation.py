"""Scene/theme changes on the leader propagate to followers over the mesh."""
import harness
from harness import Simulation
from fakes.bus import BUS


def _synced_pair():
    sim = Simulation(2)
    assert sim.boot_one(0)
    assert sim.start_followers(0)
    return sim


def test_next_scene_propagates():
    sim = _synced_pair()
    leader, follower = sim.nodes[0], sim.nodes[1]

    BUS.bind(0)
    leader.ctrl.next_scene(harness.now())
    target = leader.ctrl.status()['scene']

    sim.run(1000)
    assert follower.ctrl.status()['scene'] == target


def test_next_theme_propagates():
    sim = _synced_pair()
    leader, follower = sim.nodes[0], sim.nodes[1]

    BUS.bind(0)
    leader.ctrl.next_theme(harness.now())
    target = leader.ctrl.status()['theme']

    sim.run(1000)
    assert follower.ctrl.status()['theme'] == target
