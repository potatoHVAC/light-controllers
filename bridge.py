import time
import socket
import json
import network as _net

from secrets import PANEL_SSID, PANEL_PASSWORD

BRIDGE_PORT     = 5001
WIFI_TIMEOUT_MS = 10000


class Bridge:
    """Lightweight UDP bridge between the ESP-NOW mesh and the laptop server.

    Forwards received ESP-NOW packets to the laptop (fire-and-forget UDP).
    Receives sequenced commands from the laptop, ACKs them, deduplicates by
    sequence number so retransmits don't double-broadcast to the mesh.

    The laptop learns the bridge's IP from the first packet it receives.
    """

    def __init__(self):
        self._sock = None
        self._laptop_ip = None
        self._last_seq = -1

    def connect(self):
        """Connect to the show control hotspot. Returns True on success."""
        sta = _net.WLAN(_net.STA_IF)
        sta.active(True)
        try:
            sta.config(channel=1)
        except Exception:
            pass
        sta.connect(PANEL_SSID, PANEL_PASSWORD)

        start = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
                return False

        self._laptop_ip = sta.ifconfig()[2]  # gateway = laptop
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(('', BRIDGE_PORT))
        self._sock.setblocking(False)

        # Announce so the laptop learns our IP immediately
        self._raw_send({'type': 'bridge_connected'})
        return True

    def forward(self, packet):
        """Forward a received ESP-NOW packet to the laptop (fire-and-forget)."""
        if not self._sock or not self._laptop_ip:
            return
        msg = dict(packet)
        msg['fwd'] = True
        self._raw_send(msg)

    def tick(self):
        """Check for incoming commands from the laptop.

        Returns the command dict if it should be executed (new sequence number),
        or None if nothing arrived or the message was a duplicate.
        Always ACKs received commands so the laptop stops retrying.
        """
        if not self._sock:
            return None

        try:
            data, addr = self._sock.recvfrom(512)
        except OSError:
            return None

        try:
            msg = json.loads(data)
        except Exception:
            return None

        seq = msg.get('seq')
        if seq is None:
            return None

        # Always ACK — even duplicates, so the laptop stops retrying
        try:
            self._sock.sendto(json.dumps({'ack': seq}).encode(), addr)
        except Exception:
            pass

        if seq <= self._last_seq:
            return None  # Duplicate — already executed

        self._last_seq = seq
        return msg

    def _raw_send(self, data):
        if not self._sock or not self._laptop_ip:
            return
        try:
            self._sock.sendto(json.dumps(data).encode(), (self._laptop_ip, BRIDGE_PORT))
        except Exception:
            pass
