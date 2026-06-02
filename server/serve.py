#!/usr/bin/env python3
"""
Light Controllers server. Handles OTA firmware updates and show control bridging.

Usage:
    python3 server/serve.py

OTA updates and show control share one hotspot.
    SSID and password are read from secrets.py in the project root.
    Open http://localhost:8080/panel for the show control panel.

Note: the OTA_FILES list mirrors deploy.sh. Keep both in sync when adding files.
"""

import json
import os
import queue
import socket
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ACK_TIMEOUT = 0.5    # seconds to wait for a command ACK
MAX_RETRIES = 3      # command retry attempts before logging a warning

PROJECT_ROOT = Path(os.environ['FIRMWARE_DIR']) if 'FIRMWARE_DIR' in os.environ else Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config import DISCOVERY_PORT as UDP_PORT, DISCOVERY_MSG, BRIDGE_PORT, HTTP_PORT, THEMES
from secrets import OTA_SSID, OTA_PASSWORD, BRIDGE_SECRET
import hmac as _hmac_mod
import hashlib as _hashlib

OTA_FILES = [
    'boot.py', 'main.py', 'controller.py', 'mesh.py', 'bridge.py',
    'auth.py', 'log.py', 'ota.py', 'color.py', 'button.py', 'strip.py',
    'fixture.py', 'storage.py', 'themes.py', 'secrets.py', 'config.py',
    'patterns/__init__.py', 'patterns/base.py', 'patterns/bounce_pulse.py',
    'patterns/breathe.py', 'patterns/breathe_center.py', 'patterns/center_meet.py',
    'patterns/dna_pulse.py', 'patterns/firefly.py', 'patterns/flash_rb.py',
    'patterns/glitter.py', 'patterns/launch.py', 'patterns/rainbow.py',
    'patterns/rainbow_flash.py', 'patterns/resonance.py', 'patterns/solid.py',
    'patterns/spinner.py',
]

# ── Bridge state ──────────────────────────────────────────────────────────────

_bridge_ip          = None
_bridge_seq         = 0
_ack_queue          = queue.Queue()
_bridge_lock        = threading.Lock()
_bridge_sock        = None
_last_bridge_packet = 0.0   # time.time() of last received bridge packet
BRIDGE_TIMEOUT_S    = 15    # mark disconnected after 3× heartbeat interval

_mesh_state = {
    'theme':      None,
    'scene':      None,
    'dim':        1.0,
    'solo_active': False,
    'leader':     False,
    'autonomous': False,
    'connected':  False,
}


def _init_bridge():
    global _bridge_sock
    _bridge_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _bridge_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _bridge_sock.bind(('', BRIDGE_PORT))


def _bridge_receiver():
    """Background thread: reads UDP packets from the bridge, routes ACKs and
    forwarded mesh packets."""
    global _bridge_ip, _last_bridge_packet
    while True:
        try:
            data, addr = _bridge_sock.recvfrom(512)
            msg = json.loads(data)
        except Exception:
            continue

        _bridge_ip = addr[0]
        _last_bridge_packet = time.time()

        if 'ack' in msg:
            _ack_queue.put(msg['ack'])
            continue

        msg_type = msg.get('type')

        if msg_type == 'bridge_connected':
            with _bridge_lock:
                _mesh_state['connected'] = True
            _log(f'Bridge connected from {addr[0]}', 'ok')
            continue

        if not msg.get('fwd'):
            continue

        with _bridge_lock:
            if msg_type in ('heartbeat', 'change'):
                if msg.get('theme'):
                    _mesh_state['theme'] = msg['theme']
                if msg.get('scene'):
                    _mesh_state['scene'] = msg['scene']
                if 'dim' in msg:
                    _mesh_state['dim'] = msg['dim']
                if msg.get('leader'):
                    _mesh_state['leader'] = True
                    _mesh_state['autonomous'] = bool(msg.get('auto'))
            elif msg_type == 'solo':
                _mesh_state['solo_active'] = msg.get('active', False)
                if 'dim' in msg:
                    _mesh_state['dim'] = msg['dim']
            elif msg_type == 'hotspot_found':
                _log(f"[{msg.get('sender','?')[:8]}] hotspot alert on channel {msg.get('ch')}", 'info')
            elif msg_type == 'log':
                sender = msg.get('sender', 'unknown')[:8]
                lvl  = msg.get('lvl', 'info')
                src  = msg.get('src', '?')
                text = msg.get('msg', '')
                entry_type = 'warn' if lvl == 'warn' else ('err' if lvl == 'error' else 'info')
                _log(f'[{sender}] [{src}] {text}', entry_type)


def _sign_payload(payload_bytes):
    """HMAC-SHA256 sign payload_bytes using BRIDGE_SECRET."""
    return _hmac_mod.new(
        BRIDGE_SECRET.encode(), payload_bytes, _hashlib.sha256
    ).hexdigest()


def send_command(command):
    """Send a signed, sequenced command to the bridge. Retries up to MAX_RETRIES times.
    Commands are sent as <json>|<hmac_hex> so the controller can verify before executing.
    Logs a warning if all retries fail. Returns True if ACKed."""
    global _bridge_seq
    if not _bridge_ip:
        _log(f'Command ignored — bridge not connected: {command.get("type")}', 'warn')
        return False

    with _bridge_lock:
        _bridge_seq += 1
        seq = _bridge_seq

    command['seq'] = seq
    payload = json.dumps(command, separators=(',', ':')).encode()
    sig = _sign_payload(payload)
    data = payload + b'|' + sig.encode()

    for attempt in range(MAX_RETRIES):
        try:
            _bridge_sock.sendto(data, (_bridge_ip, BRIDGE_PORT))
            deadline = time.time() + ACK_TIMEOUT
            while time.time() < deadline:
                try:
                    ack_seq = _ack_queue.get(timeout=max(0.01, deadline - time.time()))
                    if ack_seq == seq:
                        return True
                except queue.Empty:
                    break
        except Exception:
            pass

    _log(f'Command failed after {MAX_RETRIES} retries: {command.get("type")} — '
         f'bridge may be unreachable', 'warn')
    return False


# ── Theme helpers ─────────────────────────────────────────────────────────────

def _find_theme(name):
    return next((t for t in THEMES if t['name'] == name), None)


def _next_theme_scene():
    """Compute the next theme and its first scene from current mesh state."""
    current = _mesh_state.get('theme')
    idx = next((i for i, t in enumerate(THEMES) if t['name'] == current), -1)
    theme = THEMES[(idx + 1) % len(THEMES)]
    return theme['name'], theme['scenes'][0], theme['color']


def _next_scene():
    """Compute the next scene within the current theme."""
    theme = _find_theme(_mesh_state.get('theme'))
    if not theme:
        return None, None, None
    scenes = theme['scenes']
    current = _mesh_state.get('scene')
    idx = next((i for i, s in enumerate(scenes) if s == current), -1)
    scene = scenes[(idx + 1) % len(scenes)]
    return theme['name'], scene, theme['color']


# ── Logging ───────────────────────────────────────────────────────────────────

_log_entries = []


def _log(msg, entry_type='info'):
    ts = datetime.now().strftime('%H:%M:%S')
    entry = {'type': entry_type, 'msg': f'[{ts}] {msg}'}
    _log_entries.append(entry)
    print(entry['msg'])


# ── HTML ──────────────────────────────────────────────────────────────────────

OTA_HTML = """\
<!DOCTYPE html><html>
<head><meta charset="utf-8"><title>Light Controllers OTA</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:sans-serif;background:#111;color:#ddd;padding:24px;max-width:640px;margin:0 auto}
h1{color:#4af;margin-bottom:20px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:16px}
.card.green{border-color:#3a3;background:#0f1f0f}
.card h2{font-size:15px;color:#aaa;margin-bottom:10px;text-transform:uppercase;letter-spacing:.05em}
.status{font-size:18px;color:#4a4;font-weight:bold}
ol{padding-left:20px} ol li{margin:8px 0;line-height:1.5}
code{background:#2a2a2a;padding:2px 6px;border-radius:4px;font-size:13px}
.files{font-size:12px;color:#666;column-count:2} .files div{padding:2px 0}
#log{font-family:monospace;font-size:13px;min-height:60px;max-height:280px;overflow-y:auto}
.ok{color:#4a4}.info{color:#777}.warn{color:#aa6}.err{color:#a44}.entry{padding:2px 0}
</style></head><body>
<h1>Light Controllers OTA</h1>
<div class="card green"><div class="status">&#10003; Server running &nbsp;|&nbsp;
<a href="/panel" style="color:#4af">Show Control &rarr;</a></div></div>
<div class="card"><h2>How to update a controller</h2><ol>
<li>Share a WiFi hotspot: SSID <code>OTA_SSID_VALUE</code> Password <code>OTA_PASSWORD_VALUE</code></li>
<li>Hold the button on the controller while powering it on for 3 seconds</li>
<li>Controller connects, downloads, and restarts automatically</li>
</ol></div>
<div class="card"><h2>Files being served (FILE_COUNT)</h2>
<div class="files">FILE_LIST</div></div>
<div class="card"><h2>Update log</h2>
<div id="log"><div class="entry info">Waiting...</div></div></div>
<script>
function go(){fetch('/log').then(r=>r.json()).then(e=>{
  if(!e.length)return;
  document.getElementById('log').innerHTML=e.slice(-100).map(x=>
    `<div class="entry ${x.type}">${x.msg}</div>`).join('');
  document.getElementById('log').scrollTop=9999;
}).catch(()=>{})}
go();setInterval(go,2000);
</script></body></html>
"""

PANEL_HTML = """\
<!DOCTYPE html><html>
<head><meta charset="utf-8"><title>Light Controllers</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:sans-serif;background:#111;color:#ddd;padding:20px;max-width:480px;margin:0 auto}
h1{color:#4af;margin-bottom:16px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:12px}
.status{font-size:13px;color:#aaa;margin-bottom:4px}
.status span{color:#eee;font-weight:bold}
.bridge{font-size:12px;margin-top:4px}
.bridge.on{color:#4a4}.bridge.off{color:#a44}
.row{display:flex;gap:8px;margin-top:10px}
button{flex:1;padding:12px;border:none;border-radius:6px;background:#2a4a6a;color:#eee;font-size:14px;cursor:pointer}
button:active{opacity:.8}
button.solo{background:#6a2a2a}
button.solo.active{background:#aa4444}
label{display:block;margin-top:12px;font-size:13px;color:#aaa}
input[type=range]{width:100%;margin-top:6px}
#log{font-family:monospace;font-size:12px;max-height:160px;overflow-y:auto}
.ok{color:#4a4}.info{color:#777}.warn{color:#aa6}.err{color:#a44}.entry{padding:1px 0}
</style></head><body>
<h1>Light Controllers</h1>
<div class="card">
  <div class="status">Theme: <span id="theme">—</span> &nbsp;|&nbsp;
    Scene: <span id="scene">—</span> &nbsp;|&nbsp; Dim: <span id="dim">—</span></div>
  <div id="bridge" class="bridge off">Bridge: not connected</div>
  <div id="auto" class="bridge off" style="display:none">Mesh running autonomously</div>
</div>
<div class="card">
  <div class="row">
    <button onclick="post('/next_scene')">Next Scene</button>
    <button onclick="post('/next_theme')">Next Theme</button>
  </div>
  <div class="row">
    <button onclick="post('/random_scene')">Random Scene</button>
    <button id="solobtn" class="solo" onclick="toggleSolo()">Solo Off</button>
  </div>
  <label>Dim <span id="dimval">100</span>%</label>
  <input type="range" min="0" max="100" value="100"
    oninput="document.getElementById('dimval').textContent=this.value"
    onchange="post('/dim',{dim:parseFloat(this.value)/100})">
</div>
<div class="card">
  <div style="font-size:13px;color:#aa6;margin-bottom:8px">DEPLOY</div>
  <button onclick="deployUpdate()" style="width:100%;background:#3a2a0a;color:#eee;padding:12px;border:1px solid #aa6;border-radius:6px;cursor:pointer;font-size:14px">
    Push Firmware Update to All Controllers
  </button>
  <div id="deploystatus" style="font-size:12px;color:#777;margin-top:6px"></div>
</div>
<div class="card">
  <div style="font-size:13px;color:#aaa;margin-bottom:8px">SERVER LOG</div>
  <div id="log"><div class="entry info">Loading...</div></div>
</div>
<script>
var _solo=false;
function post(path,body){
  fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body||{})}).then(load);
}
function toggleSolo(){
  _solo=!_solo;
  post(_solo?'/solo':'/release_solo');
  var b=document.getElementById('solobtn');
  b.textContent=_solo?'Solo On':'Solo Off';
  b.className='solo'+(_solo?' active':'');
}
function load(){
  fetch('/status').then(r=>r.json()).then(d=>{
    document.getElementById('theme').textContent=d.theme||'—';
    document.getElementById('scene').textContent=d.scene||'—';
    document.getElementById('dim').textContent=Math.round((d.dim||1)*100)+'%';
    var b=document.getElementById('bridge');
    b.textContent=d.connected?'Bridge: connected':'Bridge: not connected';
    b.className='bridge '+(d.connected?'on':'off');
    var a=document.getElementById('auto');
    a.style.display=d.autonomous?'block':'none';
  }).catch(()=>{});
  fetch('/log').then(r=>r.json()).then(entries=>{
    var el=document.getElementById('log');
    if(!entries.length)return;
    el.innerHTML=entries.slice(-50).map(e=>
      `<div class="entry ${e.type}">${e.msg}</div>`).join('');
    el.scrollTop=el.scrollHeight;
  }).catch(()=>{});
}
function deployUpdate(){
  var el=document.getElementById('deploystatus');
  el.textContent='Sending...';
  fetch('/deploy',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
    .then(r=>r.json()).then(d=>{
      el.textContent=d.ok?'Update sent — controllers will reboot shortly.':'Failed to reach bridge.';
      el.style.color=d.ok?'#4a4':'#a44';
    }).catch(()=>{el.textContent='Error.';el.style.color='#a44';});
}
setInterval(load,2000);load();
</script></body></html>
"""


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/', '/ota'):
            manifest = self._build_manifest()
            body = (OTA_HTML
                    .replace('OTA_SSID_VALUE', OTA_SSID)
                    .replace('OTA_PASSWORD_VALUE', OTA_PASSWORD)
                    .replace('FILE_COUNT', str(len(manifest['files'])))
                    .replace('FILE_LIST', ''.join(f'<div>{f["path"]}</div>'
                                                  for f in manifest['files']))
                    ).encode()
            self._respond(200, 'text/html', body)

        elif self.path == '/panel':
            self._respond(200, 'text/html', PANEL_HTML.encode())

        elif self.path == '/status':
            with _bridge_lock:
                state = dict(_mesh_state)
            state['connected'] = (
                _last_bridge_packet > 0 and
                time.time() - _last_bridge_packet < BRIDGE_TIMEOUT_S
            )
            self._respond(200, 'application/json', json.dumps(state).encode())

        elif self.path == '/manifest.json':
            _log(f'OTA: controller {self.client_address[0]} connected')
            manifest = self._build_manifest()
            payload = json.dumps(manifest, separators=(',', ':')).encode()
            sig = _sign_payload(payload)
            self._respond(200, 'application/octet-stream', payload + b'|' + sig.encode())

        elif self.path.startswith('/files/'):
            file_path = self.path[7:]
            full = PROJECT_ROOT / file_path
            if full.exists() and full.is_file():
                body = full.read_bytes()
                self._respond(200, 'application/octet-stream', body)
                _log(f'OTA: {self.client_address[0]} ← {file_path} ({len(body)}b)', 'ok')
            else:
                self.send_response(404)
                self.end_headers()

        elif self.path == '/log':
            self._respond(200, 'application/json',
                          json.dumps(_log_entries[-100:]).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length else '{}'
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        path = self.path
        ok = True

        if path == '/next_scene':
            theme, scene, color = _next_scene()
            if theme:
                cmd = {'type': 'change', 'theme': theme, 'scene': scene}
                if color:
                    cmd['color'] = color
                ok = send_command(cmd)

        elif path == '/next_theme':
            theme, scene, color = _next_theme_scene()
            cmd = {'type': 'change', 'theme': theme, 'scene': scene}
            if color:
                cmd['color'] = color
            ok = send_command(cmd)

        elif path == '/random_scene':
            theme_name = _mesh_state.get('theme')
            theme = _find_theme(theme_name)
            if theme:
                cmd = {'type': 'change', 'theme': theme_name, 'scene': None,
                       'color': theme['color']}
                ok = send_command(cmd)

        elif path == '/solo':
            ok = send_command({'type': 'solo', 'active': True, 'dim': 0.2})

        elif path == '/release_solo':
            ok = send_command({'type': 'solo', 'active': False, 'dim': 1.0})

        elif path == '/dim':
            dim = float(data.get('dim', 1.0))
            ok = send_command({'type': 'dim', 'dim': dim})

        elif path == '/deploy':
            _log('Deploy requested — sending OTA update to all controllers')
            ok = send_command({'type': 'ota_update'})

        else:
            self._respond(404, 'application/json', b'{"error":"not found"}')
            return

        status = 200 if ok else 502
        self._respond(status, 'application/json',
                      json.dumps({'ok': ok}).encode())

    def _build_manifest(self):
        files = []
        for path in OTA_FILES:
            full = PROJECT_ROOT / path
            if full.exists():
                files.append({'path': path, 'size': full.stat().st_size})
            else:
                _log(f'WARNING: {path} not found', 'warn')
        return {'files': files}

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

def _udp_broadcaster():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            sock.sendto(DISCOVERY_MSG, ('255.255.255.255', UDP_PORT))
        except Exception:
            pass
        time.sleep(1)


def _bridge_heartbeat():
    """Send a signed keepalive heartbeat to the bridge every 5 seconds.
    The bridge uses this to detect when the server goes offline."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        time.sleep(5)
        if not _bridge_ip:
            continue
        try:
            payload = b'{"type":"server_heartbeat"}'
            sig = _sign_payload(payload)
            sock.sendto(payload + b'|' + sig.encode(), (_bridge_ip, BRIDGE_PORT))
        except Exception:
            pass


if __name__ == '__main__':
    _init_bridge()
    manifest_files = len([f for f in OTA_FILES if (PROJECT_ROOT / f).exists()])
    _log(f'Serving {manifest_files} OTA files on port {HTTP_PORT}')
    _log(f'Hotspot SSID: {OTA_SSID}')
    _log(f'Control panel: http://localhost:{HTTP_PORT}/panel')
    threading.Thread(target=_udp_broadcaster,   daemon=True).start()
    threading.Thread(target=_bridge_receiver,   daemon=True).start()
    threading.Thread(target=_bridge_heartbeat,  daemon=True).start()
    try:
        HTTPServer(('', HTTP_PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
