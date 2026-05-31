#!/usr/bin/env python3
"""
OTA update server for Light Controllers.

Usage:
    python3 server/serve.py

Before running:
    1. Create a WiFi hotspot on this computer:
       SSID:     LIGHTRIG_OTA
       Password: lightrig2024
    2. Open http://localhost:8080 in a browser for status.

To update a controller:
    Hold the button while powering it on. Keep holding for 3 seconds.
    The controller will connect, download all files, and restart automatically.

Note: the file list below mirrors deploy.sh. Keep both in sync when adding files.
"""

import json
import os
import socket
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

UDP_PORT = 5000

PORT = 8080
PROJECT_ROOT = Path(os.environ['FIRMWARE_DIR']) if 'FIRMWARE_DIR' in os.environ else Path(__file__).parent.parent

OTA_FILES = [
    'main.py',
    'controller.py',
    'mesh.py',
    'ota.py',
    'color.py',
    'button.py',
    'strip.py',
    'fixture.py',
    'storage.py',
    'themes.py',
    'patterns/__init__.py',
    'patterns/base.py',
    'patterns/bounce_pulse.py',
    'patterns/breathe.py',
    'patterns/breathe_center.py',
    'patterns/center_meet.py',
    'patterns/dna_pulse.py',
    'patterns/firefly.py',
    'patterns/flash_rb.py',
    'patterns/glitter.py',
    'patterns/launch.py',
    'patterns/rainbow.py',
    'patterns/rainbow_flash.py',
    'patterns/resonance.py',
    'patterns/solid.py',
    'patterns/spinner.py',
]

HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Light Controllers OTA</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: sans-serif; background: #111; color: #ddd; padding: 24px; max-width: 640px; margin: 0 auto; }
    h1 { color: #4af; margin-bottom: 20px; }
    .card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    .card.green { border-color: #3a3; background: #0f1f0f; }
    .card h2 { font-size: 15px; color: #aaa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
    .status { font-size: 18px; color: #4a4; font-weight: bold; }
    ol { padding-left: 20px; }
    ol li { margin: 8px 0; line-height: 1.5; }
    code { background: #2a2a2a; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    .files { font-size: 12px; color: #666; column-count: 2; }
    .files div { padding: 2px 0; }
    #log { font-family: monospace; font-size: 13px; min-height: 60px; max-height: 280px; overflow-y: auto; }
    .ok   { color: #4a4; }
    .info { color: #777; }
    .err  { color: #a44; }
    .entry { padding: 2px 0; }
  </style>
</head>
<body>
  <h1>Light Controllers OTA</h1>

  <div class="card green">
    <div class="status">&#10003; Server running on port PORT</div>
  </div>

  <div class="card">
    <h2>How to update a controller</h2>
    <ol>
      <li>Ensure this computer is sharing a WiFi hotspot:<br>
          SSID: <code>LIGHTRIG_OTA</code> &nbsp; Password: <code>lightrig2024</code></li>
      <li>Hold the button on the controller while powering it on</li>
      <li>Keep holding for <strong>3 seconds</strong></li>
      <li>The controller connects, downloads all files, and restarts automatically</li>
    </ol>
  </div>

  <div class="card">
    <h2>Files being served (FILE_COUNT files)</h2>
    <div class="files">FILE_LIST</div>
  </div>

  <div class="card">
    <h2>Update log</h2>
    <div id="log"><div class="entry info">Waiting for connections...</div></div>
  </div>

  <script>
    function fetchLog() {
      fetch('/log').then(r => r.json()).then(entries => {
        const log = document.getElementById('log');
        if (!entries.length) return;
        log.innerHTML = entries.slice(-100).map(e =>
          `<div class="entry ${e.type}">${e.msg}</div>`
        ).join('');
        log.scrollTop = log.scrollHeight;
      }).catch(() => {});
    }
    fetchLog();
    setInterval(fetchLog, 2000);
  </script>
</body>
</html>
"""

_log_entries = []


def _log(msg, entry_type='info'):
    ts = datetime.now().strftime('%H:%M:%S')
    entry = {'type': entry_type, 'msg': f'[{ts}] {msg}'}
    _log_entries.append(entry)
    print(entry['msg'])


def _build_manifest():
    files = []
    for path in OTA_FILES:
        full = PROJECT_ROOT / path
        if full.exists():
            files.append({'path': path, 'size': full.stat().st_size})
        else:
            _log(f'WARNING: {path} not found', 'err')
    return {'files': files}


def _build_html(manifest):
    file_list = ''.join(f'<div>{f["path"]}</div>' for f in manifest['files'])
    return (HTML
            .replace('PORT', str(PORT))
            .replace('FILE_COUNT', str(len(manifest['files'])))
            .replace('FILE_LIST', file_list))


class OTAHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        client = self.client_address[0]

        if self.path == '/':
            manifest = _build_manifest()
            body = _build_html(manifest).encode()
            self._respond(200, 'text/html', body)

        elif self.path == '/manifest.json':
            _log(f'Controller {client} connected')
            manifest = _build_manifest()
            body = json.dumps(manifest).encode()
            self._respond(200, 'application/json', body)

        elif self.path.startswith('/files/'):
            file_path = self.path[7:]
            full = PROJECT_ROOT / file_path
            if full.exists() and full.is_file():
                body = full.read_bytes()
                self._respond(200, 'application/octet-stream', body)
                _log(f'Controller {client} ← {file_path} ({len(body)}b)', 'ok')
            else:
                self.send_response(404)
                self.end_headers()
                _log(f'Controller {client} requested missing file: {file_path}', 'err')

        elif self.path == '/log':
            body = json.dumps(_log_entries[-100:]).encode()
            self._respond(200, 'application/json', body)

        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # suppress default access log


def _udp_broadcaster():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            sock.sendto(b'LIGHTRIG_OTA', ('255.255.255.255', UDP_PORT))
        except Exception:
            pass
        time.sleep(1)


if __name__ == '__main__':
    manifest = _build_manifest()
    _log(f'Serving {len(manifest["files"])} files on port {PORT}')
    _log('Open http://localhost:8080 in your browser')
    _log('Waiting for controllers...')
    threading.Thread(target=_udp_broadcaster, daemon=True).start()
    try:
        HTTPServer(('', PORT), OTAHandler).serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
