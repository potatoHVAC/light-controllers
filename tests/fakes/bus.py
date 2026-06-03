"""Shared in-memory radio bus for the fake hardware.

Models the one thing that matters for the mesh protocol: ESP-NOW only delivers
between peers on the same WiFi channel. Each simulated controller is a "node"
with its own channel and inbox. The harness binds the active node before
constructing or ticking a controller, so the fake WLAN/ESPNow instances created
by that controller attach to the right node.
"""
from collections import deque


class _Node:
    def __init__(self, nid):
        self.id        = nid
        self.channel   = 1
        self.inbox     = deque()
        self.assoc     = False   # associated with a hotspot
        self.connecting = None   # ssid currently connecting to


class Bus:
    def __init__(self):
        self.nodes    = {}
        self.active   = None
        self.hotspots = {}       # ssid -> channel (simulated access points)

    def reset(self):
        self.nodes.clear()
        self.active = None
        self.hotspots.clear()

    def bind(self, nid):
        """Make nid the active node; fake WLAN/ESPNow bind to it at creation."""
        self.active = nid
        if nid not in self.nodes:
            self.nodes[nid] = _Node(nid)
        return self.nodes[nid]

    def node(self, nid):
        return self.nodes[nid]

    def broadcast(self, sender_id, data):
        ch = self.nodes[sender_id].channel
        for nid, n in self.nodes.items():
            if nid != sender_id and n.channel == ch:
                n.inbox.append((sender_id, data))

    def recv(self, nid):
        n = self.nodes[nid]
        return n.inbox.popleft() if n.inbox else (None, None)


BUS = Bus()
