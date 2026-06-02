import time
import socket
import json
import network as _net

from secrets import OTA_SSID, OTA_PASSWORD, BRIDGE_SECRET
from config import BRIDGE_PORT, DISCOVERY_PORT, DISCOVERY_MSG
from auth import verify as _verify_sig

WIFI_TIMEOUT_MS     = 10000
DISCOVER_TIMEOUT_MS = 3000


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
        """Connect to the show control hotspot. Returns True on success.

        On any failure, calls sta.disconnect() (not sta.active(False)) so the
        WiFi radio stays up for ESP-NOW on the same interface.
        """
        sta = _net.WLAN(_net.STA_IF)
        sta.active(True)
        sta.connect(OTA_SSID, OTA_PASSWORD)

        start = time.ticks_ms()
        while not sta.isconnected():
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            if elapsed > WIFI_TIMEOUT_MS:
                sta.disconnect()
                return False
            # Fast-fail on auth errors (wrong password) — don't wait full timeout
            status = sta.status()
            if status in (202, 203, 204):
                sta.disconnect()
                return False

        # Discover the laptop's IP via its UDP broadcast — the gateway is the
        # phone hotspot, not the laptop, so we can't use ifconfig()[2].
        laptop_ip = self._discover_laptop()
        if laptop_ip is None:
            sta.disconnect()
            return False

        self._laptop_ip = laptop_ip
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(('', BRIDGE_PORT))
        self._sock.setblocking(False)

        # Announce so the laptop learns our IP immediately
        self._raw_send({'type': 'bridge_connected'})
        return True

    def _discover_laptop(self):
        """Listen for the server's OTA discovery broadcast to find its IP."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            sock.bind(('', DISCOVERY_PORT))
            start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start) < DISCOVER_TIMEOUT_MS:
                try:
                    data, addr = sock.recvfrom(64)
                    if data == DISCOVERY_MSG:
                        sock.close()
                        return addr[0]
                except OSError:
                    pass
            sock.close()
        except Exception:
            pass
        return None

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

        # Commands arrive as <json_bytes>|<hmac_hex> — verify before parsing.
        sep = data.rfind(b'|')
        if sep < 0:
            return None
        payload = data[:sep]
        sig_hex = data[sep + 1:].decode()
        if not _verify_sig(BRIDGE_SECRET, payload, sig_hex):
            return None  # Reject unsigned or tampered commands

        try:
            msg = json.loads(payload)
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
