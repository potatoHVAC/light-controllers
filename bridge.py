import time
import socket
import json
import network as _net

from secrets import OTA_SSID, OTA_PASSWORD, BRIDGE_SECRET
from config import BRIDGE_PORT, DISCOVERY_PORT, DISCOVERY_MSG
from auth import verify as _verify_sig
from mesh import scan_channel as _scan_channel

WIFI_TIMEOUT_MS      = 10000
DISCOVER_TIMEOUT_MS  = 5000
SERVER_TIMEOUT_MS    = 15000  # reset if no server heartbeat for 15 seconds

# Connection state machine states
_IDLE        = 0
_CONNECTING  = 1
_DISCOVERING = 2
_CONNECTED   = 3


class Bridge:
    """Non-blocking UDP bridge between the ESP-NOW mesh and the laptop server.

    Call tick_connect() every main loop iteration until is_connected() is True.
    Once connected, call tick() every loop iteration to send/receive packets.

    State machine:
        IDLE → CONNECTING  : tick_connect() starts WiFi connection
        CONNECTING → DISCOVERING : WiFi connected, start UDP discovery
        DISCOVERING → CONNECTED  : server broadcast received
        Any → IDLE         : timeout or error, caller schedules retry
    """

    def __init__(self, mesh):
        self._mesh               = mesh
        self._state              = _IDLE
        self._sock               = None
        self._laptop_ip          = None
        self._last_seq           = -1
        self._state_start        = 0
        self._sta                = None
        self._disc_sock          = None
        self._last_server_hb_ms  = None  # last received server heartbeat
        self._hint_channel       = None  # known channel from a hotspot_found alert

    def set_channel_hint(self, ch):
        """Supply a known hotspot channel so the next attempt skips the scan."""
        self._hint_channel = ch

    def is_connected(self):
        return self._state == _CONNECTED

    def start_connect(self, channel=None):
        """Begin a connection attempt. Scans for the hotspot (blocking ~2s)
        unless channel is supplied (e.g. from a hotspot_found alert), announces
        the channel to the mesh so followers migrate first, then associates.
        Returns False if no hotspot is found (caller backs off)."""
        ch = channel if channel is not None else _scan_channel(OTA_SSID)
        if ch is None:
            return False
        # Tell the mesh to move BEFORE we associate and get dragged off-channel.
        self._mesh.announce_channel(ch)
        self._mesh.apply_channel(ch)
        self._sta = _net.WLAN(_net.STA_IF)
        self._sta.active(True)
        self._sta.connect(OTA_SSID, OTA_PASSWORD)
        self._state       = _CONNECTING
        self._state_start = time.ticks_ms()
        return True

    def tick_connect(self, now_ms):
        """Advance the connection state machine one step. Returns True when
        connected, False if the attempt failed (caller should retry later),
        None if still in progress."""

        if self._state == _CONNECTED:
            return True

        if self._state == _IDLE:
            hint = self._hint_channel
            self._hint_channel = None
            if self.start_connect(hint) is False:
                return False
            return None

        if self._state == _CONNECTING:
            if self._sta.isconnected():
                # WiFi up — open discovery socket and move to next state
                try:
                    self._disc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._disc_sock.setblocking(False)
                    self._disc_sock.bind(('', DISCOVERY_PORT))
                except Exception:
                    self._fail()
                    return False
                self._state       = _DISCOVERING
                self._state_start = now_ms
                return None

            elapsed = time.ticks_diff(now_ms, self._state_start)
            if elapsed > WIFI_TIMEOUT_MS:
                self._fail()
                return False

            # Fast-fail on auth errors
            status = self._sta.status()
            if status in (202, 203, 204):
                self._fail()
                return False

            return None  # still connecting

        if self._state == _DISCOVERING:
            # Check for server broadcast
            try:
                data, addr = self._disc_sock.recvfrom(64)
                if data == DISCOVERY_MSG:
                    self._close_disc_sock()
                    self._laptop_ip = addr[0]
                    self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._sock.bind(('', BRIDGE_PORT))
                    self._sock.setblocking(False)
                    self._state = _CONNECTED
                    self._raw_send({'type': 'bridge_connected'})
                    return True
            except OSError:
                pass

            if time.ticks_diff(now_ms, self._state_start) > DISCOVER_TIMEOUT_MS:
                self._fail()
                return False

            return None  # still discovering

        return None

    def _fail(self):
        self._close_disc_sock()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._sta:
            try:
                self._sta.disconnect()
            except Exception:
                pass
        self._state = _IDLE

    def _close_disc_sock(self):
        if self._disc_sock:
            try:
                self._disc_sock.close()
            except Exception:
                pass
            self._disc_sock = None

    def forward(self, packet):
        """Forward a received ESP-NOW packet to the laptop (fire-and-forget)."""
        if not self._sock or not self._laptop_ip:
            return
        msg = dict(packet)
        msg['fwd'] = True
        self._raw_send(msg)

    def tick(self):
        """Check for incoming commands from the laptop. Non-blocking.

        Returns the command dict if one should be executed, else None.
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
            return None

        try:
            msg = json.loads(payload)
        except Exception:
            return None

        seq = msg.get('seq')
        if seq is None:
            return None

        try:
            self._sock.sendto(json.dumps({'ack': seq}).encode(), addr)
        except Exception:
            pass

        if seq <= self._last_seq:
            return None

        self._last_seq = seq

        # Heartbeat from server — update timestamp, don't execute as a command
        if msg.get('type') == 'server_heartbeat':
            self._last_server_hb_ms = time.ticks_ms()
            return None

        return msg

    def check_server_alive(self, now_ms):
        """Return False and reset to IDLE if server heartbeats have gone silent."""
        if self._state != _CONNECTED:
            return True
        if self._last_server_hb_ms is None:
            return True
        if time.ticks_diff(now_ms, self._last_server_hb_ms) > SERVER_TIMEOUT_MS:
            self._fail()
            return False
        return True

    def _raw_send(self, data):
        if not self._sock or not self._laptop_ip:
            return
        try:
            self._sock.sendto(json.dumps(data).encode(), (self._laptop_ip, BRIDGE_PORT))
        except Exception:
            pass
