import time
import espnow
import json
import network as _net
import ubinascii
import random

from config import DEFAULT_CHANNEL, SET_CHANNEL_REPEATS

BROADCAST = b'\xff\xff\xff\xff\xff\xff'


def scan_channel(ssid):
    """Blocking WiFi scan (~2s) for ssid. Returns its channel, or None if not
    found. Permitted only at a connect/recovery moment, never in steady state."""
    try:
        sta = _net.WLAN(_net.STA_IF)
        sta.active(True)
        target = ssid.encode() if isinstance(ssid, str) else ssid
        for ap in sta.scan():
            if ap[0] == target:
                return ap[2]  # channel field
    except Exception:
        pass
    return None


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
        self._sta = _net.WLAN(_net.STA_IF)
        self._sta.active(True)
        # Every controller boots on the same known channel so the mesh is
        # coherent before any hotspot announcement migrates it elsewhere.
        self._channel = DEFAULT_CHANNEL
        try:
            self._sta.config(channel=DEFAULT_CHANNEL)
        except Exception:
            pass
        self._en = espnow.ESPNow()
        self._en.active(True)
        self._en.add_peer(BROADCAST)
        self._mac = ubinascii.hexlify(self._sta.config('mac')).decode()
        self._last_any_packet_ms = time.ticks_ms()  # for orphan/silence detection
        self._seq = 0
        self._last_seqs = {}      # sender_mac -> last accepted seq
        self._last_seen = {}      # sender_mac -> now_ms of last packet
        self._pending = {}        # nonce -> {'deadline': ms, 'count': n}
        self._is_leader = False
        self._leader_mac = None
        self._last_leader_hb_ms = None
        self._autonomous = False        # this leader has given up finding a server
        self._mesh_autonomous = False   # observed: the current leader is autonomous
        self._fw = None                 # firmware version (reported in heartbeats)
        self._cfg = None                # config version (reported in heartbeats)
        self._upd_fail = None           # last rolled-back update version, or None
        self._pending_retry = None  # (type, ..., fire_at_ms) for critical retransmit
        # Reusable packet dict — mutated in place on every _broadcast() to avoid
        # allocating a new dict (and triggering GC) on every send.
        self._pkt = {'type': None, 'sender': self._mac, 'seq': 0,
                     'theme': None, 'scene': None, 'dim': 1.0}
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

    @property
    def channel(self):
        return self._channel

    @property
    def autonomous(self):
        return self._autonomous

    def set_autonomous(self, value):
        """Leader declares (or clears) autonomous mode — broadcast in heartbeats."""
        self._autonomous = value

    @property
    def mesh_autonomous(self):
        """True if the current leader's heartbeats report autonomous mode."""
        return self._mesh_autonomous

    def send_hotspot_found(self, ch):
        """A follower tells the leader a hotspot exists on channel ch, so the
        leader can resume connecting even after it gave up scanning. Bursted a
        few times so a single dropped packet doesn't leave the leader asleep."""
        for _ in range(SET_CHANNEL_REPEATS):
            self._send_typed('hotspot_found', ch=ch)

    def set_versions(self, fw, cfg, update_failed=None):
        """Set this controller's firmware version and config version, reported
        in heartbeats so the server knows who is up to date and configured.
        update_failed: the version of a rolled-back update (admin flag), or None."""
        self._fw = fw
        self._cfg = cfg
        self._upd_fail = update_failed

    # Targeted relays: the leader rebroadcasts a server command onto the mesh so
    # the addressed controller (target == its MAC, or None for all) acts on it.
    def send_identify(self, target):
        self._send_typed('identify', target=target)

    def send_solo_request(self, target, dim=None):
        self._send_typed('solo_request', target=target, dim=dim)

    def send_solo_tag(self, tag, dim=None, active=True):
        self._send_typed('solo_tag', tag=tag, dim=dim, active=active)

    def send_force_leader(self, target):
        self._send_typed('force_leader', target=target)

    def send_default(self):
        self._send_typed('default')

    def send_set_config(self, target, config):
        self._send_typed('set_config', target=target, config=config)

    def _send_typed(self, msg_type, **fields):
        """Broadcast a small typed control message (sender + seq + extra fields)."""
        self._seq += 1
        packet = {'type': msg_type, 'sender': self._mac, 'seq': self._seq}
        packet.update(fields)
        self._send(packet)

    def silent_for(self, now_ms):
        """Milliseconds since any mesh packet was last received from a peer.
        Used to detect a controller orphaned on the wrong channel."""
        return time.ticks_diff(now_ms, self._last_any_packet_ms)

    def apply_channel(self, ch):
        """Switch the radio to channel ch. No-op if already there."""
        if ch == self._channel:
            return
        try:
            self._sta.config(channel=ch)
            self._channel = ch
            self._last_any_packet_ms = time.ticks_ms()  # don't instantly trip silence
        except Exception:
            pass

    def announce_channel(self, ch):
        """Burst-broadcast set_channel on the CURRENT channel so followers move
        before the leader associates and gets dragged off. Call before switching."""
        for _ in range(SET_CHANNEL_REPEATS):
            self._seq += 1
            self._send({
                'type':   'set_channel',
                'sender': self._mac,
                'seq':    self._seq,
                'ch':     ch,
            })

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
        pick a random scene from the theme independently.
        Sent twice with a short gap to improve delivery reliability."""
        self._seq += 1
        self._broadcast('change', theme, scene, dim, color=color)
        self._pending_retry = ('change', theme, scene, dim, color,
                               time.ticks_add(time.ticks_ms(), 200))

    def send_solo(self, active, dim=0.2):
        """Broadcast solo state. active=True dims all others; False restores full brightness.
        Sent twice with a short gap to improve delivery reliability."""
        self._seq += 1
        self._pkt['type']   = 'solo'
        self._pkt['seq']    = self._seq
        self._pkt['active'] = active
        self._pkt['dim']    = dim if active else 1.0
        self._pkt.pop('theme', None)
        self._pkt.pop('scene', None)
        self._pkt.pop('color', None)
        self._pkt.pop('nonce', None)
        self._send(self._pkt)
        self._pending_retry = ('solo', active, dim, None, None,
                               time.ticks_add(time.ticks_ms(), 200))

    def send_log(self, source, msg, level='info'):
        """Broadcast a log entry. The bridge picks it up and forwards to the server."""
        self._seq += 1
        self._send({
            'type':   'log',
            'sender': self._mac,
            'seq':    self._seq,
            'src':    source,
            'lvl':    level,
            'msg':    msg,
            't':      time.ticks_ms(),
        })

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

    def tick(self, theme, scene, dim, now_ms, color=None, master_dim=None, personal=False):
        """Send heartbeat if due, fire or suppress pending responses, return any valid incoming message."""
        if time.ticks_diff(now_ms, self._last_heartbeat_ms) >= self.HEARTBEAT_MS:
            self._last_heartbeat_ms = now_ms
            self._seq += 1
            self._broadcast('heartbeat', theme, scene, dim, color=color,
                            master_dim=master_dim, personal=personal)

        if self._pending_retry:
            msg_type = self._pending_retry[0]
            fire_at  = self._pending_retry[5]
            if time.ticks_diff(now_ms, fire_at) >= 0:
                if msg_type == 'change':
                    _, t, s, d, c, _ = self._pending_retry
                    self._seq += 1
                    self._broadcast('change', t, s, d, color=c)
                elif msg_type == 'solo':
                    _, active, d, _, _, _ = self._pending_retry
                    self._seq += 1
                    self._pkt['type']   = 'solo'
                    self._pkt['seq']    = self._seq
                    self._pkt['active'] = active
                    self._pkt['dim']    = d if active else 1.0
                    self._pkt.pop('theme', None)
                    self._pkt.pop('scene', None)
                    self._pkt.pop('color', None)
                    self._pkt.pop('nonce', None)
                    self._send(self._pkt)
                self._pending_retry = None

        for nonce in list(self._pending):
            entry = self._pending[nonce]
            if entry['count'] >= self.SUPPRESS_THRESHOLD:
                del self._pending[nonce]
            elif time.ticks_diff(now_ms, entry['deadline']) >= 0:
                self._seq += 1
                self._broadcast('heartbeat', theme, scene, dim, nonce=nonce, color=color,
                                master_dim=master_dim, personal=personal)
                self._last_heartbeat_ms = now_ms
                del self._pending[nonce]

        try:
            _, msg = self._en.recv(0)
        except Exception:
            # recv() can raise if the ESP-NOW receive buffer is exhausted (heap
            # fragmentation). Run GC to compact before the next tick rather than
            # propagating the error into the main loop.
            import gc; gc.collect()
            return None
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
        self._last_seen[sender] = now_ms
        self._last_any_packet_ms = now_ms  # heard a peer — not orphaned

        # Prune senders not heard from in 5× heartbeat interval to prevent
        # unbounded memory growth over long sessions or with many controllers.
        prune_ms = self.HEARTBEAT_MS * 5
        for mac in list(self._last_seen):
            if time.ticks_diff(now_ms, self._last_seen[mac]) > prune_ms:
                self._last_seqs.pop(mac, None)
                del self._last_seen[mac]

        msg_type = data.get('type')

        if msg_type == 'set_channel':
            self.apply_channel(data.get('ch', self._channel))
            return None

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
                # Track whether the leader has gone autonomous (no server found)
                self._mesh_autonomous = bool(data.get('auto'))
            return data

        return data

    def _broadcast(self, msg_type, theme, scene, dim=1.0, nonce=None, color=None, master_dim=None, personal=False):
        self._pkt['type']   = msg_type
        self._pkt['seq']    = self._seq
        self._pkt['theme']  = theme
        self._pkt['scene']  = scene
        self._pkt['dim']    = dim
        if master_dim is not None:
            self._pkt['master_dim'] = master_dim
        elif 'master_dim' in self._pkt:
            del self._pkt['master_dim']
        if personal:
            self._pkt['personal'] = True
        elif 'personal' in self._pkt:
            del self._pkt['personal']
        if self._is_leader:
            self._pkt['leader'] = True
            if self._autonomous:
                self._pkt['auto'] = True
            elif 'auto' in self._pkt:
                del self._pkt['auto']
        else:
            if 'leader' in self._pkt:
                del self._pkt['leader']
            if 'auto' in self._pkt:
                del self._pkt['auto']
        if color is not None:
            self._pkt['color'] = list(color)
        elif 'color' in self._pkt:
            del self._pkt['color']
        if nonce is not None:
            self._pkt['nonce'] = nonce
        elif 'nonce' in self._pkt:
            del self._pkt['nonce']
        # Identity for the server registry (null until set at boot).
        self._pkt['fw'] = self._fw
        self._pkt['cfg'] = self._cfg
        if self._upd_fail is not None:
            self._pkt['upd_fail'] = self._upd_fail
        elif 'upd_fail' in self._pkt:
            del self._pkt['upd_fail']
        self._send(self._pkt)

    def _send(self, data):
        try:
            self._en.send(BROADCAST, json.dumps(data))
        except Exception:
            pass
