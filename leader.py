import network as _net
import socket
import json

from secrets import PANEL_SSID, PANEL_PASSWORD

PANEL_PORT = 80

_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Light Controllers</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:sans-serif;background:#111;color:#ddd;padding:20px;max-width:480px;margin:0 auto}
    h1{color:#4af;margin-bottom:20px}
    .card{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:12px}
    .status{font-size:14px;color:#aaa}
    .status span{color:#eee;font-weight:bold}
    .row{display:flex;gap:10px;margin-top:10px}
    button{flex:1;padding:12px;border:none;border-radius:6px;background:#2a4a6a;color:#eee;font-size:15px;cursor:pointer}
    button:active{background:#1a3a5a}
    button.solo{background:#6a2a2a}
    button.solo.active{background:#aa4444}
    label{display:block;margin-top:10px;font-size:13px;color:#aaa}
    input[type=range]{width:100%;margin-top:6px}
  </style>
</head>
<body>
  <h1>Light Controllers</h1>
  <div class="card">
    <div class="status">
      Theme: <span id="theme">—</span> &nbsp;|&nbsp;
      Scene: <span id="scene">—</span> &nbsp;|&nbsp;
      Dim: <span id="dim">—</span>
    </div>
  </div>
  <div class="card">
    <div class="row">
      <button onclick="post('/next_scene')">Next Scene</button>
      <button onclick="post('/next_theme')">Next Theme</button>
    </div>
    <div class="row">
      <button onclick="post('/random_scene')">Random Scene</button>
      <button id="solobtn" class="solo" onclick="toggleSolo()">Solo</button>
    </div>
    <label>Dim <span id="dimval">100</span>%</label>
    <input type="range" min="0" max="100" value="100"
           oninput="document.getElementById('dimval').textContent=this.value"
           onchange="post('/dim',{dim:this.value/100})">
  </div>
  <script>
    var _solo = false;
    function post(path,body){
      fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
        body:body?JSON.stringify(body):'{}'}).then(load);
    }
    function toggleSolo(){
      _solo=!_solo;
      post(_solo?'/solo':'/release_solo');
      document.getElementById('solobtn').className='solo'+(_solo?' active':'');
    }
    function load(){
      fetch('/status').then(r=>r.json()).then(d=>{
        document.getElementById('theme').textContent=d.theme||'—';
        document.getElementById('scene').textContent=d.scene||'—';
        document.getElementById('dim').textContent=Math.round((d.dim||1)*100)+'%';
      }).catch(()=>{});
    }
    setInterval(load,2000);
    load();
  </script>
</body>
</html>
"""


def start_ap():
    """Start the control panel WiFi AP on channel 1 (same as ESP-NOW)."""
    ap = _net.WLAN(_net.AP_IF)
    ap.active(True)
    ap.config(
        essid=PANEL_SSID,
        password=PANEL_PASSWORD,
        channel=1,
        authmode=3,  # WPA2
    )
    return ap


class HttpServer:
    """Non-blocking HTTP server. Call tick() every loop iteration."""

    def __init__(self, port=PANEL_PORT):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('', port))
        self._sock.listen(1)
        self._sock.setblocking(False)
        self._conn = None
        self._buf  = b''

    def tick(self):
        """Check for a complete incoming request. Returns (method, path, body) or None."""
        if self._conn is None:
            try:
                self._conn, _ = self._sock.accept()
                self._conn.setblocking(False)
                self._buf = b''
            except OSError:
                return None

        try:
            chunk = self._conn.recv(512)
            if chunk:
                self._buf += chunk
            else:
                self._conn.close()
                self._conn = None
                return None
        except OSError:
            return None

        if b'\r\n\r\n' not in self._buf:
            return None

        try:
            header, _, body = self._buf.partition(b'\r\n\r\n')
            line = header.decode().split('\r\n')[0].split(' ')
            return (line[0], line[1] if len(line) > 1 else '/', body.decode())
        except Exception:
            self._conn.close()
            self._conn = None
            return None

    def respond(self, body, status=200, content_type='text/html'):
        if self._conn is None:
            return
        try:
            resp = (
                'HTTP/1.1 {} OK\r\n'
                'Content-Type: {}\r\n'
                'Content-Length: {}\r\n'
                'Connection: close\r\n\r\n{}'
            ).format(status, content_type, len(body), body)
            self._conn.sendall(resp.encode())
        except OSError:
            pass
        finally:
            self._conn.close()
            self._conn = None

    def respond_json(self, data, status=200):
        self.respond(json.dumps(data), status=status, content_type='application/json')

    def respond_html(self):
        self.respond(_HTML, content_type='text/html')

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
        self._sock.close()
