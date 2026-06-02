"""Test harness: a controllable clock and a multi-node mesh simulation.

The clock augments the real `time` module with MicroPython's ticks_* functions,
reading a counter the tests advance. The Simulation builds real Controller +
Mesh + Fixture + Strip instances (only the hardware modules are faked) and steps
them against the shared bus, so integration tests exercise the actual code.
"""
import time

from fakes.bus import BUS

TICKS_PERIOD = 1 << 30
_now = [0]


def install():
    """Patch MicroPython ticks_* onto the real time module."""
    time.ticks_ms   = ticks_ms
    time.ticks_add  = ticks_add
    time.ticks_diff = ticks_diff
    time.sleep_ms   = sleep_ms


def reset_clock(t=0):
    _now[0] = t % TICKS_PERIOD


def advance(dt):
    _now[0] = (_now[0] + dt) % TICKS_PERIOD


def now():
    return _now[0]


def ticks_ms():
    return _now[0]


def ticks_add(t, d):
    return (t + d) % TICKS_PERIOD


def ticks_diff(a, b):
    d = (a - b) & (TICKS_PERIOD - 1)
    if d >= TICKS_PERIOD // 2:
        d -= TICKS_PERIOD
    return d


def sleep_ms(ms):
    advance(ms)


# ── Simulation ────────────────────────────────────────────────────────────────

def default_themes():
    from themes import RandomTheme, ColorTheme
    return [RandomTheme(), ColorTheme((255, 0, 0), 'red'), ColorTheme((0, 0, 255), 'blue')]


class Node:
    """One simulated controller and everything it owns."""

    def __init__(self, nid, themes_factory=default_themes):
        from strip import Strip
        from fixture import Fixture
        from mesh import Mesh
        from controller import Controller
        BUS.bind(nid)
        self.id      = nid
        strips       = [Strip('primary', 26, 3), Strip('secondary', 22, 3)]
        self.fixture = Fixture(strips)
        self.mesh    = Mesh()
        self.ctrl    = Controller(self.fixture, themes_factory(), network=self.mesh)
        self.started = False

    @property
    def channel(self):
        return BUS.node(self.id).channel

    def begin(self):
        BUS.bind(self.id)
        self.ctrl.begin(now())

    def step_start(self, button=False):
        BUS.bind(self.id)
        if not self.started:
            self.started = self.ctrl.tick_start(now(), button)
        return self.started

    def step(self):
        BUS.bind(self.id)
        self.ctrl.update(now())


class Simulation:
    """A set of nodes sharing one bus and clock."""

    def __init__(self, n, themes_factory=default_themes):
        BUS.reset()
        reset_clock(0)
        self.nodes = [Node(i, themes_factory) for i in range(n)]

    def begin_all(self):
        for nd in self.nodes:
            nd.begin()

    def run_start(self, max_ms=20000, dt=10):
        """Drive every node's startup concurrently until all have started."""
        self.begin_all()
        elapsed = 0
        while elapsed < max_ms and not all(nd.started for nd in self.nodes):
            for nd in self.nodes:
                nd.step_start()
            advance(dt)
            elapsed += dt
        return all(nd.started for nd in self.nodes)

    def run(self, ms, dt=10):
        """Run the steady-state loop for ms milliseconds.

        Each node drains its inbox within a time slice — on hardware the main
        loop runs thousands of times per second, so it clears pending packets
        almost immediately. Modelling one packet per coarse 10ms step instead
        would make convergence look artificially slow."""
        for _ in range(ms // dt):
            for nd in self.nodes:
                nd.step()
                guard = 0
                while BUS.node(nd.id).inbox and guard < 200:
                    nd.step()
                    guard += 1
            advance(dt)

    def leaders(self):
        return [nd for nd in self.nodes if nd.ctrl.is_leader]

    def boot_one(self, i, max_ms=8000, dt=10):
        """Boot node i alone — with no peers talking, it reaches the election
        timeout and becomes leader."""
        nd = self.nodes[i]
        nd.begin()
        elapsed = 0
        while not nd.started and elapsed < max_ms:
            nd.step_start()
            advance(dt)
            elapsed += dt
        return nd.started

    def start_followers(self, leader_i, max_ms=20000, dt=10):
        """Start every other node while the leader runs, so they sync as followers."""
        others = [nd for j, nd in enumerate(self.nodes) if j != leader_i]
        for nd in others:
            nd.begin()
        elapsed = 0
        while elapsed < max_ms and not all(nd.started for nd in others):
            self.nodes[leader_i].step()
            for nd in others:
                nd.step_start()
            advance(dt)
            elapsed += dt
        return all(nd.started for nd in others)
