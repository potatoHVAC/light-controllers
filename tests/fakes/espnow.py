"""Fake espnow backed by the shared bus."""
from fakes.bus import BUS


class ESPNow:
    def __init__(self):
        self._nid = BUS.active

    def active(self, value=True):
        return True

    def add_peer(self, mac):
        pass

    def send(self, mac, data):
        BUS.broadcast(self._nid, data)

    def recv(self, timeout=0):
        return BUS.recv(self._nid)
