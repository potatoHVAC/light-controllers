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

    The leader flag is included in heartbeats when this controller is the leader.
    Followers use this to detect leader loss and trigger re-election.
    """

    HEARTBEAT_MS       = 5000
    JITTER_MAX_MS      = 500
    SUPPRESS_THRESHOLD = 3

    def __init__(self):
        sta = _net.WLAN(_net.STA_IF)
        sta.active(True)
        self._en = espnow.ESPNow()
        self._en.active(True)
        self._en.add_peer(BROADCAST)
        self._mac = ubinascii.hexlify(sta.config('mac')).decode()
        self._seq = 0
        self._last_seqs = {}
        self._pending = {}  # nonce -> {'deadline': ms, 'count': n}
        self._is_leader = False
        self._leader_mac = None
        self._last_leader_hb_ms = None
        # Set last heartbeat far in the past so the first tick() fires immediately.
        self._last_heartbeat_ms = time.ticks_add(time.ticks_ms(), -self.HEARTBEAT_MS)

    @property
    def mac(self):
        return self._mac

    @property
    def is_leader(self):
        return self._is_leader

    @is_leader.setter
    def is_leader(self, value):
        self._is_leader = value

    @property
    def leader_mac(self):
        return self._leader_mac

    def note_leader_heartbeat(self, sender_mac, now_ms):
        """Record that a leader heartbeat was received from sender_mac."""
        self._leader_mac = sender_mac
        self._last_leader_hb_ms = now_ms

    def leader_heartbeat_age(self, now_ms):
        """Milliseconds since last leader heartbeat, or None if never seen."""
        if self._last_leader_hb_ms is None:
            return None
        return time.ticks_diff(now_ms, self._last_leader_hb_ms)

    def announce(self):
        """Broadcast a heartbeat_request after sync is complete to announce presence."""
        self._seq += 1
        self._send({
            'type': 'heartbeat_request',
            'sender': self._mac,
            'seq': self._seq,
            'nonce': random.randint(0, 0xFFFFFF),
        })

    def send_change(self, theme, scene, dim=1.0, color=None):
        """Broadcast a theme+scene change. scene=None tells each receiver to
        pick a random scene from the theme independently."""
        self._seq += 1
        self._broadcast('change', theme, scene, dim, color=color)

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

    def send_ota_update(self):
        """Broadcast an OTA update request to all controllers in the mesh."""
        self._seq += 1
        self._send({
            'type': 'ota_update',
            'sender': self._mac,
            'seq': self._seq,
        })

    def send_dim(self, dim):
        """Broadcast a dim-only command without changing theme or scene."""
        self._seq += 1
        self._send({
            'type': 'dim',
            'sender': self._mac,
            'seq': self._seq,
            'dim': dim,
        })

    def tick(self, theme, scene, dim, now_ms, color=None):
        """Send heartbeat if due, fire or suppress pending responses, return any valid incoming message."""
        if time.ticks_diff(now_ms, self._last_heartbeat_ms) >= self.HEARTBEAT_MS:
            self._last_heartbeat_ms = now_ms
            self._seq += 1
            self._broadcast('heartbeat', theme, scene, dim, color=color)

        for nonce in list(self._pending):
            entry = self._pending[nonce]
            if entry['count'] >= self.SUPPRESS_THRESHOLD:
                del self._pending[nonce]
            elif time.ticks_diff(now_ms, entry['deadline']) >= 0:
                self._seq += 1
                self._broadcast('heartbeat', theme, scene, dim, nonce=nonce, color=color)
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
            if data.get('leader'):
                self.note_leader_heartbeat(sender, now_ms)
            return data

        return data

    def _broadcast(self, msg_type, theme, scene, dim=1.0, nonce=None, color=None):
        packet = {
            'type': msg_type,
            'sender': self._mac,
            'seq': self._seq,
            'theme': theme,
            'scene': scene,
            'dim': dim,
        }
        if self._is_leader:
            packet['leader'] = True
        if color is not None:
            packet['color'] = list(color)
        if nonce is not None:
            packet['nonce'] = nonce
        self._send(packet)

    def _send(self, data):
        try:
            self._en.send(BROADCAST, json.dumps(data))
        except Exception:
            pass
