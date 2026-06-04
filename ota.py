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

_ORANGE = (255, 80, 0)   # "writing flash, do not power off" — matches main.py
_GREEN  = (0, 255, 0)
_BLACK  = (0, 0, 0)

_DANGER_LEDS    = 3
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


def _danger(np):
    """Solid orange on the first few LEDs: a flash write is in progress and
    power must not be cut. Clamped to the strip length (works on a 1-LED strip)."""
    np.fill(_BLACK)
    for i in range(min(_DANGER_LEDS, len(np))):
        np[i] = _ORANGE
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


def _discover_server(feed=None):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.bind(('', UDP_PORT))
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < DISCOVER_TIMEOUT_MS:
            if feed:
                feed()
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


def run(np=None, feed=None):
    """Check for OTA server and download update if found.

    Files are downloaded into /update/ and verified before writing
    /update_ready. The actual swap to root happens on the next boot
    in main.py, so a power cut during download leaves the running
    firmware completely untouched.

    WiFi is always shut down before returning so ESP-NOW initialises
    cleanly regardless of how this function exits.

    feed: optional watchdog-feed callback. The download outlasts the watchdog
    timeout, so it is fed through the connect/discovery/download loops.

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
            if feed:
                feed()
            if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
                return False

        server_ip = _discover_server(feed)
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

        # Orange "do not power off" marker for the whole flash-writing phase.
        if np:
            _danger(np)

        for i, f in enumerate(files):
            if feed:
                feed()
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
                        if feed:
                            feed()
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

        # Stash the firmware version alongside the staged files so the A/B swap
        # copies it to root; the controller then reports it to the server.
        try:
            with open(UPDATE_DIR + '/firmware_version', 'w') as vf:
                vf.write(manifest.get('version', ''))
        except Exception:
            pass

        with open(UPDATE_READY, 'w') as mf:
            mf.write('1')

        if np:
            _flash_done(np)

        result = True
        return result

    finally:
        sta.active(False)
