"""LeaderLink backoff lifecycle: ramp up, declare autonomous after the 40s
interval, give up after the cap retries, and resume on a hotspot alert."""
import harness
import bridge as bridge_mod
from leader_link import LeaderLink


class FakeMesh:
    def __init__(self):
        self.autonomous = False
        self.mac = 'aabbcc'
        self._fw = None
        self._cfg = None
        self._upd_fail = None

    def set_autonomous(self, v):
        self.autonomous = v


class FakeController:
    is_leader      = True
    theme          = 'red'
    scene          = 'solid'
    dim            = 1.0
    master_dim     = 1.0
    _personal_mode = False


class FakeBridge:
    connect_result = False        # what tick_connect returns

    def __init__(self, mesh):
        self.mesh = mesh
        self.hint = None
        self._connected = False   # like the real Bridge: False until tick_connect wins

    def set_channel_hint(self, ch): self.hint = ch
    def is_connected(self):         return self._connected
    def tick_connect(self, now):
        if self.connect_result is True:
            self._connected = True
        return self.connect_result
    def check_server_alive(self, now): return True
    def tick(self):                 return None
    def forward(self, pkt):         pass


def _fail_cycle(link, ctrl):
    # Jump well past any backoff interval, then create + attempt (two ticks).
    harness.advance(400000)
    link.tick(ctrl, harness.now())   # creates the bridge
    link.tick(ctrl, harness.now())   # attempt -> fails


def test_declares_autonomous_after_40s_interval(monkeypatch):
    monkeypatch.setattr(bridge_mod, 'Bridge', FakeBridge)
    FakeBridge.connect_result = False
    mesh, ctrl = FakeMesh(), FakeController()
    link = LeaderLink(mesh)

    # Backoff: 5s,10s,20s,40s -> the 40s failure flips autonomous on.
    for _ in range(3):
        _fail_cycle(link, ctrl)
        assert mesh.autonomous is False
    _fail_cycle(link, ctrl)              # the 40s interval fails
    assert mesh.autonomous is True


def test_gives_up_after_cap_retries(monkeypatch):
    monkeypatch.setattr(bridge_mod, 'Bridge', FakeBridge)
    FakeBridge.connect_result = False
    mesh, ctrl = FakeMesh(), FakeController()
    link = LeaderLink(mesh)

    for _ in range(20):                  # plenty to ramp up and exhaust the cap
        _fail_cycle(link, ctrl)

    # Once given up it stops creating bridges, even when the retry timer elapses.
    harness.advance(400000)
    link.tick(ctrl, harness.now())
    assert link.bridge is None


def test_resume_on_alert_reconnects(monkeypatch):
    monkeypatch.setattr(bridge_mod, 'Bridge', FakeBridge)
    FakeBridge.connect_result = False
    mesh, ctrl = FakeMesh(), FakeController()
    link = LeaderLink(mesh)
    for _ in range(20):
        _fail_cycle(link, ctrl)          # give up

    # A follower reports a hotspot; next attempt succeeds.
    FakeBridge.connect_result = True
    link.on_alert(ctrl, {'type': 'hotspot_found', 'ch': 6}, harness.now())
    link.tick(ctrl, harness.now())       # creates bridge with the hint
    assert link.bridge.hint == 6
    link.tick(ctrl, harness.now())       # connects
    assert link.connected()
    assert mesh.autonomous is False


def test_non_leader_does_nothing(monkeypatch):
    monkeypatch.setattr(bridge_mod, 'Bridge', FakeBridge)
    mesh = FakeMesh()
    ctrl = FakeController(); ctrl.is_leader = False
    link = LeaderLink(mesh)
    assert link.tick(ctrl, harness.now()) is None
    assert link.bridge is None
