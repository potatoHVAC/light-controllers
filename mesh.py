import time
import espnow
import json
import network as _net
import ubinascii

BROADCAST = b'\xff\xff\xff\xff\xff\xff'


class Mesh:
    """ESP-NOW broadcast mesh. Every controller hears every other controller.

    Each outgoing message is tagged with the sender's MAC and a sequence
    number. Receivers ignore messages from themselves and drop anything with
    a sequence number no higher than the last accepted message from that sender.

    On boot each controller broadcasts a hello. Any controller that receives
    a hello immediately replies with a heartbeat carrying its current state,
    so the newcomer syncs within one round trip instead of waiting up to
    HEARTBEAT_MS.
    """

    HEARTBEAT_MS = 5000

    def __init__(self):
        sta = _net.WLAN(_net.STA_IF)
        sta.active(True)
        self._en = espnow.ESPNow()
        self._en.active(True)
        self._en.add_peer(BROADCAST)
        self._mac = ubinascii.hexlify(sta.config('mac')).decode()
        self._seq = 0
        self._last_seqs = {}
        self._last_heartbeat_ms = 0
        self._seq += 1
        self._send({'type': 'heartbeat_request', 'sender': self._mac, 'seq': self._seq})

    SYNC_TIMEOUT_MS = 2000

    def wait_for_sync(self, timeout_ms=None):
        """Block waiting for a state message from the network.
        Returns (theme, scene) if received, None if timeout elapsed."""
        timeout_ms = timeout_ms if timeout_ms is not None else self.SYNC_TIMEOUT_MS
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            _, msg = self._en.recv(0)
            if not msg:
                continue
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if data.get('sender') == self._mac:
                continue
            if data.get('type') in ('heartbeat', 'change'):
                return data.get('theme', 0), data.get('scene', 0)
        return None

    def send_change(self, theme, scene):
        """Broadcast a scene change initiated by this controller."""
        self._seq += 1
        self._broadcast('change', theme, scene)

    def tick(self, theme, scene, now_ms):
        """Send heartbeat if due and return any valid incoming message, or None."""
        if time.ticks_diff(now_ms, self._last_heartbeat_ms) >= self.HEARTBEAT_MS:
            self._last_heartbeat_ms = now_ms
            self._seq += 1
            self._broadcast('heartbeat', theme, scene)

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

        if data.get('type') == 'heartbeat_request':
            self._seq += 1
            self._broadcast('heartbeat', theme, scene)
            self._last_heartbeat_ms = now_ms
            return None

        return data

    def _broadcast(self, msg_type, theme, scene):
        self._send({
            'type': msg_type,
            'sender': self._mac,
            'seq': self._seq,
            'theme': theme,
            'scene': scene,
        })

    def _send(self, data):
        try:
            self._en.send(BROADCAST, json.dumps(data))
        except Exception:
            pass
