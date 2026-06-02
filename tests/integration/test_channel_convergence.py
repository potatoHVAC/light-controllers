"""The whole mesh migrates to a new channel together and keeps working —
the end-to-end version of the set_channel protocol the bridge drives."""
import harness
from harness import Simulation
from fakes.bus import BUS


def _synced_trio():
    sim = Simulation(3)
    assert sim.boot_one(0)
    assert sim.start_followers(0)
    return sim


def test_mesh_migrates_together():
    sim = _synced_trio()
    assert all(n.channel == 1 for n in sim.nodes)

    # The leader migrates exactly as the bridge would: announce on the current
    # channel, then move itself.
    BUS.bind(0)
    sim.nodes[0].mesh.announce_channel(6)
    sim.nodes[0].mesh.apply_channel(6)

    sim.run(1500)
    assert all(n.channel == 6 for n in sim.nodes)


def test_control_still_works_after_migration():
    sim = _synced_trio()
    BUS.bind(0)
    sim.nodes[0].mesh.announce_channel(6)
    sim.nodes[0].mesh.apply_channel(6)
    sim.run(1500)

    BUS.bind(0)
    sim.nodes[0].ctrl.next_scene(harness.now())
    target = sim.nodes[0].ctrl.status()['scene']
    sim.run(1000)

    assert sim.nodes[1].ctrl.status()['scene'] == target
    assert sim.nodes[2].ctrl.status()['scene'] == target
