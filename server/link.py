"""The bridge link: signed UDP comms with the leader controller, plus the live
controller registry and mesh-state derived from forwarded packets.

Socket I/O (start) is separate from message processing (handle_packet) so the
routing/registry logic can be unit-tested without a network.
"""
import hashlib
import hmac
import json
import queue
import socket
import threading
import time

ACK_TIMEOUT          = 0.5
MAX_RETRIES          = 3
BRIDGE_TIMEOUT_S     = 15    # mesh "connected" if a packet arrived within this
CONTROLLER_TIMEOUT_S = 20    # a controller is "online" if heard within this


def _entry():
    return {'last_seen': 0.0, 'fw': None, 'cfg': None,
            'theme': None, 'scene': None, 'dim': 1.0, 'leader': False}


class BridgeLink:
    def __init__(self, secret, bridge_port, discovery_port, discovery_msg, log):
        self._secret         = secret
        self._bridge_port    = bridge_port
        self._discovery_port = discovery_port
        self._discovery_msg  = discovery_msg
        self._log            = log
        self._sock           = None
        self._bridge_ip      = None
        self._seq            = 0
        self._ack_queue      = queue.Queue()
        self._lock           = threading.Lock()
        self._last_packet    = 0.0
        self.registry        = {}     # mac -> info dict
        self.mesh_state = {
            'theme': None, 'scene': None, 'dim': 1.0,
            'solo_active': False, 'leader': False, 'autonomous': False,
        }

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('', self._bridge_port))
        threading.Thread(target=self._receive_loop,    daemon=True).start()
        threading.Thread(target=self._discovery_loop,  daemon=True).start()
        threading.Thread(target=self._heartbeat_loop,  daemon=True).start()

    def _receive_loop(self):
        while True:
            try:
                data, addr = self._sock.recvfrom(1024)
                msg = json.loads(data)
            except Exception:
                continue
            self.handle_packet(msg, addr)

    def _discovery_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            try:
                sock.sendto(self._discovery_msg, ('255.255.255.255', self._discovery_port))
            except Exception:
                pass
            time.sleep(1)

    def _heartbeat_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while True:
            time.sleep(5)
            if self._bridge_ip:
                try:
                    payload = b'{"type":"server_heartbeat"}'
                    sock.sendto(payload + b'|' + self._sign(payload).encode(),
                                (self._bridge_ip, self._bridge_port))
                except Exception:
                    pass

    # ── inbound ──────────────────────────────────────────────────────────────

    def handle_packet(self, msg, addr):
        """Process one parsed packet from the bridge: ACKs, connection notices,
        and forwarded mesh packets (updating registry + mesh_state)."""
        self._bridge_ip   = addr[0]
        self._last_packet = time.time()

        if 'ack' in msg:
            self._ack_queue.put(msg['ack'])
            return

        mtype = msg.get('type')
        if mtype == 'bridge_connected':
            self._log.write(f'Bridge connected from {addr[0]}', 'ok')
            return
        if not msg.get('fwd'):
            return

        sender = msg.get('sender')
        if sender:
            info = self.registry.setdefault(sender, _entry())
            info['last_seen'] = time.time()
            if 'fw' in msg:
                info['fw'] = msg['fw']
            if 'cfg' in msg:
                info['cfg'] = msg['cfg']

        if mtype in ('heartbeat', 'change'):
            if msg.get('theme'):
                self.mesh_state['theme'] = msg['theme']
            if msg.get('scene'):
                self.mesh_state['scene'] = msg['scene']
            if 'dim' in msg:
                self.mesh_state['dim'] = msg['dim']
            if sender:
                info['theme'] = msg.get('theme', info['theme'])
                info['scene'] = msg.get('scene', info['scene'])
                info['dim']   = msg.get('dim', info['dim'])
                info['leader'] = bool(msg.get('leader'))
            if msg.get('leader'):
                self.mesh_state['leader'] = True
                self.mesh_state['autonomous'] = bool(msg.get('auto'))
        elif mtype == 'solo':
            self.mesh_state['solo_active'] = msg.get('active', False)
            if 'dim' in msg:
                self.mesh_state['dim'] = msg['dim']
        elif mtype == 'hotspot_found':
            self._log.write(f"[{(sender or '?')[:8]}] hotspot alert on channel {msg.get('ch')}", 'info')
        elif mtype == 'log':
            lvl = msg.get('lvl', 'info')
            entry = 'warn' if lvl == 'warn' else ('err' if lvl == 'error' else 'info')
            self._log.write(f"[{(sender or '?')[:8]}] [{msg.get('src','?')}] {msg.get('msg','')}", entry)

    # ── outbound ─────────────────────────────────────────────────────────────

    def _sign(self, payload_bytes):
        return hmac.new(self._secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    def send_command(self, command, target=None):
        """Sign and send a command to the leader, retrying until ACKed.
        `target` (a controller MAC) scopes the command to one controller."""
        if not self._bridge_ip or not self._sock:
            self._log.write(f'Command ignored — bridge not connected: {command.get("type")}', 'warn')
            return False
        with self._lock:
            self._seq += 1
            command['seq'] = self._seq
        if target is not None:
            command['target'] = target

        payload = json.dumps(command, separators=(',', ':')).encode()
        data = payload + b'|' + self._sign(payload).encode()

        for _ in range(MAX_RETRIES):
            try:
                self._sock.sendto(data, (self._bridge_ip, self._bridge_port))
                deadline = time.time() + ACK_TIMEOUT
                while time.time() < deadline:
                    try:
                        if self._ack_queue.get(timeout=max(0.01, deadline - time.time())) == command['seq']:
                            return True
                    except queue.Empty:
                        break
            except Exception:
                pass
        self._log.write(f'Command failed after {MAX_RETRIES} retries: {command.get("type")}', 'warn')
        return False

    # ── views ────────────────────────────────────────────────────────────────

    def connected(self):
        return self._last_packet > 0 and time.time() - self._last_packet < BRIDGE_TIMEOUT_S

    def online(self, timeout=CONTROLLER_TIMEOUT_S):
        """Prune stale controllers and return {mac: info} for those still online."""
        cutoff = time.time() - timeout
        for mac in [m for m, i in self.registry.items() if i['last_seen'] < cutoff]:
            del self.registry[mac]
        return dict(self.registry)
