"""Leader election and follower sync across real Controller + Mesh instances."""
import harness
from harness import Simulation
from fakes.bus import BUS


def test_lone_controller_becomes_leader():
    sim = Simulation(1)
    assert sim.boot_one(0)
    assert sim.nodes[0].ctrl.is_leader


def test_followers_sync_to_existing_leader():
    sim = Simulation(3)
    assert sim.boot_one(0)
    assert sim.start_followers(0)
    assert sim.nodes[0].ctrl.is_leader
    assert not sim.nodes[1].ctrl.is_leader
    assert not sim.nodes[2].ctrl.is_leader


def test_two_leaders_resolve_to_lowest_mac():
    # Boot two nodes in isolation (different channels) so each elects itself,
    # then put them on the same channel — the higher MAC must stand down.
    sim = Simulation(2)
    BUS.node(1).channel = 11          # isolate node 1 during its election
    assert sim.boot_one(0)
    assert sim.boot_one(1)
    assert sim.nodes[0].ctrl.is_leader and sim.nodes[1].ctrl.is_leader

    BUS.node(1).channel = 1           # rejoin — leaders now hear each other
    for _ in range(2000):
        sim.nodes[0].step()
        sim.nodes[1].step()
        harness.advance(10)

    leaders = [n for n in sim.nodes if n.ctrl.is_leader]
    assert len(leaders) == 1
    # node 0 has the lower MAC (derived from id), so it wins.
    assert leaders[0].id == 0
