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


def test_force_leader_hands_off():
    # Admin forces a non-leader controller to become the bridge leader. The
    # relaying leader broadcasts the command and steps down; the target takes over.
    sim = Simulation(3)
    assert sim.boot_one(0)
    assert sim.start_followers(0)
    leader, follower, target = sim.nodes
    assert leader.ctrl.is_leader

    # Replicate what the relaying leader does in app._execute_bridge_command:
    BUS.bind(0)
    leader.mesh.send_force_leader(target.mesh.mac)
    leader.ctrl.step_down()

    sim.run(2000)

    assert target.ctrl.is_leader
    assert not leader.ctrl.is_leader
    assert not follower.ctrl.is_leader
    assert len(sim.leaders()) == 1


def test_force_leader_does_not_block_reelection():
    # After a forced switch, if the new leader dies, reelection still works.
    sim = Simulation(2)
    assert sim.boot_one(0)
    assert sim.start_followers(0)
    old, target = sim.nodes

    BUS.bind(0)
    old.mesh.send_force_leader(target.mesh.mac)
    old.ctrl.step_down()
    sim.run(1000)
    assert target.ctrl.is_leader

    # Target goes silent — the remaining controller must reelect itself.
    BUS.node(1).channel = 11   # isolate the target so its heartbeats stop reaching old
    for _ in range(2000):
        old.step()
        harness.advance(10)
    assert old.ctrl.is_leader


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
