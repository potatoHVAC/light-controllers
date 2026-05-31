import time
import espnow
import json
import network as _net
import ubinascii
import random

BROADCAST = b'\xff\xff\xff\xff\xff\xff'


class Mesh:
    """ESP-NOW broadcast mesh. Every controller hears every other controller.

    Each outgoing message is tagged with the sender's MAC and a sequence
    number. Receivers ignore messages from themselves and drop anything with
    a sequence number no higher than the last accepted message from that sender.

    On boot each controller broadcasts a heartbeat_request with a random nonce.
    Receivers schedule a response after a random jitter delay (0–JITTER_MAX_MS).
    While waiting, each receiver counts how many other controllers have already
    responded with that nonce. Once SUPPRESS_THRESHOLD responses are seen the
    pending response is cancelled — the newcomer already has enough data. This
    keeps the response storm bounded regardless of network size.
    """

    HEARTBEAT_MS       = 5000
    JITTER_MAX_MS      = 500
    SUPPRESS_THRESHOLD = 3

    def __init__(self):
        sta = _net.WLAN(_net.STA_IF)
        sta.active(True)
        try:
            sta.config(channel=1)
        except Exception:
            pass
        self._en = espnow.ESPNow()
        self._en.active(True)
        self._en.add_peer(BROADCAST)
        self._mac = ubinascii.hexlify(sta.config('mac')).decode()
        self._seq = 0
        self._last_seqs = {}
        self._pending = {}  # nonce -> {'deadline': ms, 'count': n}
        # Set last heartbeat far in the past so the first tick() call fires
        # a heartbeat immediately rather than waiting a full HEARTBEAT_MS.
        self._last_heartbeat_ms = time.ticks_add(time.ticks_ms(), -self.HEARTBEAT_MS)

    def announce(self):
        """Broadcast a heartbeat_request after sync is complete to announce presence."""
        self._seq += 1
        self._send({
            'type': 'heartbeat_request',
            'sender': self._mac,
            'seq': self._seq,
            'nonce': random.randint(0, 0xFFFFFF),
        })

    def send_change(self, theme, scene, dim=1.0):
        """Broadcast a scene change initiated by this controller."""
        self._seq += 1
        self._broadcast('change', theme, scene, dim)

    def send_solo(self, active, dim=0.2):
        """Broadcast solo state. active=True dims all others; False restores full brightness."""
        self._seq += 1
        packet = {
            'type': 'solo',
            'sender': self._mac,
            'seq': self._seq,
            'active': active,
            'dim': dim if active else 1.0,
        }
        self._send(packet)

    def send_dim(self, dim):
        """Broadcast a dim-only command without changing theme or scene."""
        self._seq += 1
        self._send({
            'type': 'dim',
            'sender': self._mac,
            'seq': self._seq,
            'dim': dim,
        })

    def tick(self, theme, scene, dim, now_ms):
        """Send heartbeat if due, fire or suppress pending responses, return any valid incoming message."""
        if time.ticks_diff(now_ms, self._last_heartbeat_ms) >= self.HEARTBEAT_MS:
            self._last_heartbeat_ms = now_ms
            self._seq += 1
            self._broadcast('heartbeat', theme, scene, dim)

        for nonce in list(self._pending):
            entry = self._pending[nonce]
            if entry['count'] >= self.SUPPRESS_THRESHOLD:
                del self._pending[nonce]
            elif time.ticks_diff(now_ms, entry['deadline']) >= 0:
                self._seq += 1
                self._broadcast('heartbeat', theme, scene, dim, nonce=nonce)
                self._last_heartbeat_ms = now_ms
                del self._pending[nonce]

        _, msg = self._en.recv(0)
        if not msg:
            return None
        try:
            data = json.loads(msg)
        except Exception:
            return None

        sender = data.get('sender')
        if sender == self._mac:
            return None

        seq = data.get('seq', 0)
        if seq <= self._last_seqs.get(sender, -1):
            return None

        self._last_seqs[sender] = seq
        msg_type = data.get('type')

        if msg_type == 'heartbeat_request':
            nonce = data.get('nonce')
            self._pending[nonce] = {
                'deadline': time.ticks_add(now_ms, random.randint(0, self.JITTER_MAX_MS)),
                'count': 0,
            }
            return None

        if msg_type == 'heartbeat':
            nonce = data.get('nonce')
            if nonce and nonce in self._pending:
                self._pending[nonce]['count'] += 1
            return data

        return data

    def _broadcast(self, msg_type, theme, scene, dim=1.0, nonce=None):
        packet = {
            'type': msg_type,
            'sender': self._mac,
            'seq': self._seq,
            'theme': theme,
            'scene': scene,
            'dim': dim,
        }
        if nonce is not None:
            packet['nonce'] = nonce
        self._send(packet)

    def _send(self, data):
        try:
            self._en.send(BROADCAST, json.dumps(data))
        except Exception:
            pass
