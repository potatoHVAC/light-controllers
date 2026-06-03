"""Fake network.WLAN backed by the shared bus.

Channel is per-node radio state. Associating with a known hotspot drags the
node's channel to the hotspot's channel — exactly the hardware behaviour the
channel-convergence protocol works around.
"""
from fakes.bus import BUS

STA_IF = 0
AP_IF  = 1


class WLAN:
    def __init__(self, iface=STA_IF):
        self._iface = iface
        self._nid   = BUS.active

    def active(self, value=None):
        return True

    def config(self, *args, **kwargs):
        n = BUS.node(self._nid)
        if 'channel' in kwargs:
            n.channel = kwargs['channel']
            return None
        if args:
            key = args[0]
            if key == 'channel':
                return n.channel
            if key == 'mac':
                return bytes([0, 0, 0, 0, (self._nid >> 8) & 0xFF, self._nid & 0xFF])
        return None

    def connect(self, ssid, password):
        n = BUS.node(self._nid)
        n.connecting = ssid
        ch = BUS.hotspots.get(ssid)
        if ch is not None:
            n.assoc = True
            n.channel = ch        # association drags the radio to the AP channel
        else:
            n.assoc = False

    def isconnected(self):
        return BUS.node(self._nid).assoc

    def status(self):
        n = BUS.node(self._nid)
        if n.assoc:
            return 1010                       # GOT_IP
        return 201 if BUS.hotspots.get(n.connecting) is None else 1001  # NO_AP_FOUND / CONNECTING

    def disconnect(self):
        BUS.node(self._nid).assoc = False

    def scan(self):
        return [(ssid.encode(), b'\x00' * 6, ch, -50, 0, False)
                for ssid, ch in BUS.hotspots.items()]

    def ifconfig(self):
        return ('192.168.4.2', '255.255.255.0', '192.168.4.1', '8.8.8.8')
