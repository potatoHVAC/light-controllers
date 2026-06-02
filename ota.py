import time
import network
import urequests
import socket
import os

from secrets import OTA_SSID, OTA_PASSWORD, BRIDGE_SECRET
from config import DISCOVERY_PORT, DISCOVERY_MSG, HTTP_PORT as OTA_PORT
from auth import verify as _verify_sig

UDP_PORT            = DISCOVERY_PORT
CHUNK_SIZE          = 512
WIFI_TIMEOUT_MS     = 5000
DISCOVER_TIMEOUT_MS = 1000

UPDATE_DIR   = '/update'
UPDATE_READY = '/update_ready'

_YELLOW = (128, 128, 0)
_GREEN  = (0, 255, 0)
_BLACK  = (0, 0, 0)

_PROGRESS_CYCLE = [1, 2, 3, 0]
_DONE_FLASHES   = 3
_DONE_FLASH_MS  = 300


def _busy_wait(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        pass


def _flash_done(np):
    """Signal a completed download: 3 green flashes at 300ms intervals."""
    for _ in range(_DONE_FLASHES):
        np.fill(_GREEN); np.write()
        _busy_wait(_DONE_FLASH_MS)
        np.fill(_BLACK); np.write()
        _busy_wait(_DONE_FLASH_MS)


def _set_progress(np, leds_on):
    np.fill(_BLACK)
    for i in range(leds_on):
        np[i] = _YELLOW
    np.write()


def _rm_tree(path):
    try:
        for f in os.listdir(path):
            _rm_tree(path + '/' + f)
        os.rmdir(path)
    except OSError:
        os.remove(path)


def _ensure_dir(path):
    """Create parent directories for the given path if they don't exist."""
    parts = path.split('/')
    if len(parts) > 1:
        try:
            os.mkdir('/'.join(parts[:-1]))
        except OSError:
            pass


def _discover_server():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.bind(('', UDP_PORT))
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < DISCOVER_TIMEOUT_MS:
            try:
                data, addr = sock.recvfrom(64)
                if data == DISCOVERY_MSG:
                    sock.close()
                    return addr[0]
            except OSError:
                pass
        sock.close()
    except Exception:
        pass
    return None


def run(np=None):
    """Check for OTA server and download update if found.

    Files are downloaded into /update/ and verified before writing
    /update_ready. The actual swap to root happens on the next boot
    in main.py, so a power cut during download leaves the running
    firmware completely untouched.

    WiFi is always shut down before returning so ESP-NOW initialises
    cleanly regardless of how this function exits.

    Returns True if a verified update is staged, False otherwise.
    """
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    result = False

    try:
        # Scan first so we only attempt a connection when the hotspot is
        # visible. Faster to fail than risking a premature NO_AP_FOUND status.
        target = OTA_SSID.encode()
        try:
            visible = any(n[0] == target for n in sta.scan())
        except Exception:
            visible = False

        if not visible:
            return False

        sta.connect(OTA_SSID, OTA_PASSWORD)
        start = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
                return False

        server_ip = _discover_server()
        if server_ip is None:
            return False

        base = 'http://{}:{}'.format(server_ip, OTA_PORT)

        try:
            resp = urequests.get(base + '/manifest.json')
            raw = resp.content
            resp.close()
        except Exception:
            return False

        # Manifest arrives as <json_bytes>|<hmac_hex> — verify before parsing.
        sep = raw.rfind(b'|')
        if sep < 0 or not _verify_sig(BRIDGE_SECRET, raw[:sep], raw[sep+1:].decode()):
            return False

        try:
            import ujson
            manifest = ujson.loads(raw[:sep])
        except Exception:
            return False

        files = manifest.get('files', [])

        # Clean up any previous incomplete download and start fresh
        try:
            _rm_tree(UPDATE_DIR)
        except Exception:
            pass
        os.mkdir(UPDATE_DIR)

        for i, f in enumerate(files):
            if np:
                _set_progress(np, _PROGRESS_CYCLE[i % 4])

            path = f['path']
            update_path = UPDATE_DIR + '/' + path
            try:
                resp = urequests.get(base + '/files/' + path)
                _ensure_dir(update_path)
                with open(update_path, 'wb') as fh:
                    while True:
                        chunk = resp.raw.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        fh.write(chunk)
                resp.close()
            except Exception:
                _rm_tree(UPDATE_DIR)
                return False

        for f in files:
            try:
                if os.stat(UPDATE_DIR + '/' + f['path'])[6] != f['size']:
                    _rm_tree(UPDATE_DIR)
                    return False
            except Exception:
                _rm_tree(UPDATE_DIR)
                return False

        with open(UPDATE_READY, 'w') as mf:
            mf.write('1')

        if np:
            _flash_done(np)

        result = True
        return result

    finally:
        sta.active(False)
