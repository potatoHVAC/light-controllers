import network
import espnow
import json

BROADCAST = b'\xff\xff\xff\xff\xff\xff'


class Network:
    def __init__(self):
        self._sta = network.WLAN(network.STA_IF)
        self._sta.active(True)
        self._en = espnow.ESPNow()
        self._en.active(True)
        self._en.add_peer(BROADCAST)

    def broadcast_pattern(self, index):
        self._en.send(BROADCAST, json.dumps({'pattern': index}))

    def receive(self):
        host, msg = self._en.recv(0)
        if msg:
            try:
                return json.loads(msg)
            except Exception:
                return None
        return None
