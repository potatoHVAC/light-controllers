"""Light Controllers server entry point.

Run from the project root:  python3 -m server.app

Serves the control panel (default page), the admin page, the JSON API, and the
OTA firmware endpoints. Wires together the SQLite db, the bridge link, and the
firmware manifest, and starts the bridge background threads.
"""
import hashlib
import hmac
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(os.environ['FIRMWARE_DIR']) if 'FIRMWARE_DIR' in os.environ else Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DISCOVERY_PORT, DISCOVERY_MSG, BRIDGE_PORT, HTTP_PORT, THEMES
from secrets import BRIDGE_SECRET

from server import firmware
from server.db import Database
from server.link import BridgeLink
from server.serverlog import ServerLog
from server.api import Api

STATIC_DIR = Path(__file__).parent / 'static'
DB_PATH    = os.environ.get('LIGHTRIG_DB', str(Path(__file__).parent / 'lightrig.db'))

_CTYPES = {
    '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
    '.webmanifest': 'application/manifest+json', '.json': 'application/json',
}

# Built once in main(); referenced by the handler (one instance per request).
_api  = None
_link = None
_log  = None


# Action tables keep the handler a thin dispatcher.
def _post_routes():
    return {
        '/api/next_scene':         lambda a, d: a.next_scene(),
        '/api/next_theme':         lambda a, d: a.next_theme(),
        '/api/random_scene':       lambda a, d: a.random_scene(),
        '/api/random_theme_scene': lambda a, d: a.random_theme_scene(),
        '/api/release_solo':       lambda a, d: a.release_solo(),
        '/api/solo':               lambda a, d: a.solo_controller(d['mac']),
        '/api/dim':                lambda a, d: a.dim(d.get('dim', 1.0)),
        '/api/default_show':       lambda a, d: a.default_show(),
        '/api/default_user':       lambda a, d: a.default_user(),
        '/api/deploy_all':         lambda a, d: a.deploy_all(),
        '/api/deploy_outdated':    lambda a, d: a.deploy_outdated(),
        '/api/identify':           lambda a, d: a.identify(d['mac']),
        '/api/push_config':        lambda a, d: a.push_config(d['mac']),
        '/api/delete_config':      lambda a, d: a.delete_config(d['mac']),
        '/api/save_config':        lambda a, d: a.save_config(
                                       d['mac'], d.get('fields', {}), d.get('tags')),
        '/api/defaults':           lambda a, d: a.update_defaults(d.get('fields', {})),
    }


def _get_routes():
    return {
        '/api/status':      lambda a, q: a.status(),
        '/api/controllers': lambda a, q: a.controllers(),
        '/api/defaults':    lambda a, q: a.defaults(),
        '/api/tags':        lambda a, q: a.tags(),
        '/api/themes':      lambda a, q: a.themes(),
        '/api/log':         lambda a, q: a.log(),
        '/api/config':      lambda a, q: a.config(q.get('mac', [None])[0]),
    }


class Handler(BaseHTTPRequestHandler):
    POST = _post_routes()
    GET  = _get_routes()

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if path == '/':
            return self._static('control.html')
        if path == '/admin':
            return self._static('admin.html')
        if path == '/manifest.webmanifest':
            return self._static('manifest.webmanifest')
        if path.startswith('/static/'):
            return self._static(path[len('/static/'):])

        if path in self.GET:
            return self._json(200, self.GET[path](_api, query))

        if path == '/manifest.json':
            return self._signed(json.dumps(firmware.manifest(PROJECT_ROOT),
                                           separators=(',', ':')).encode())
        if path.startswith('/files/'):
            full = PROJECT_ROOT / path[len('/files/'):]
            if full.exists() and full.is_file():
                return self._raw(200, 'application/octet-stream', full.read_bytes())
            return self._raw(404, 'text/plain', b'not found')

        self._raw(404, 'text/plain', b'not found')

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        try:
            data = json.loads(self.rfile.read(length).decode()) if length else {}
        except Exception:
            data = {}
        route = self.POST.get(urlparse(self.path).path)
        if not route:
            return self._json(404, {'error': 'not found'})
        try:
            result = route(_api, data)
        except KeyError as e:
            return self._json(400, {'error': f'missing field {e}'})
        if isinstance(result, bool):
            return self._json(200 if result else 502, {'ok': result})
        return self._json(200, result)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _static(self, name):
        full = (STATIC_DIR / name).resolve()
        if not str(full).startswith(str(STATIC_DIR.resolve())) or not full.is_file():
            return self._raw(404, 'text/plain', b'not found')
        ctype = _CTYPES.get(full.suffix, 'application/octet-stream')
        self._raw(200, ctype, full.read_bytes())

    def _signed(self, payload):
        sig = hmac.new(BRIDGE_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        self._raw(200, 'application/octet-stream', payload + b'|' + sig.encode())

    def _json(self, code, obj):
        self._raw(code, 'application/json', json.dumps(obj).encode())

    def _raw(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def build(db_path=DB_PATH):
    """Wire the app components. Returns (api, link, log) — used by tests too."""
    global _api, _link, _log
    _log  = ServerLog()
    db    = Database(db_path)
    _link = BridgeLink(BRIDGE_SECRET, BRIDGE_PORT, DISCOVERY_PORT, DISCOVERY_MSG, _log)
    _api  = Api(db, _link, _log, PROJECT_ROOT, THEMES)
    return _api, _link, _log


def main():
    build()
    _link.start()
    _log.write(f'Light Controllers server on port {HTTP_PORT}')
    _log.write(f'Control panel: http://localhost:{HTTP_PORT}/   admin: /admin')
    try:
        HTTPServer(('', HTTP_PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')


if __name__ == '__main__':
    main()
