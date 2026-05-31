import time
import network
import urequests
import socket
import os

OTA_SSID            = 'LIGHTRIG_OTA'
OTA_PASSWORD        = 'lightrig2024'
OTA_PORT            = 8080
UDP_PORT            = 5000
CHUNK_SIZE          = 512
WIFI_TIMEOUT_MS     = 5000
DISCOVER_TIMEOUT_MS = 2000

_YELLOW = (128, 128, 0)
_GREEN  = (0, 255, 0)
_BLACK  = (0, 0, 0)

_PROGRESS_CYCLE = [1, 2, 3, 0]


def _set_progress(np, leds_on):
    np.fill(_BLACK)
    for i in range(leds_on):
        np[i] = _YELLOW
    np.write()


def _ensure_dir(path):
    parts = path.split('/')
    if len(parts) > 1:
        try:
            os.mkdir('/'.join(parts[:-1]))
        except OSError:
            pass


def _hotspot_visible(sta):
    """Return True if OTA_SSID is visible in a WiFi scan."""
    target = OTA_SSID.encode()
    try:
        return any(n[0] == target for n in sta.scan())
    except Exception:
        return False


def _discover_server():
    """Listen for UDP broadcast from OTA server. Returns IP or None."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.bind(('', UDP_PORT))
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < DISCOVER_TIMEOUT_MS:
            try:
                data, addr = sock.recvfrom(64)
                if data == b'LIGHTRIG_OTA':
                    sock.close()
                    return addr[0]
            except OSError:
                pass
        sock.close()
    except Exception:
        pass
    return None


def run(np=None):
    """Check for OTA server and update if found.
    Returns True if update completed successfully, False otherwise."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)

    if not _hotspot_visible(sta):
        sta.active(False)
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
        manifest = resp.json()
        resp.close()
    except Exception:
        return False

    files = manifest.get('files', [])

    for i, f in enumerate(files):
        if np:
            _set_progress(np, _PROGRESS_CYCLE[i % 4])

        path = f['path']
        try:
            resp = urequests.get(base + '/files/' + path)
            _ensure_dir(path)
            with open(path, 'wb') as fh:
                while True:
                    chunk = resp.raw.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    fh.write(chunk)
            resp.close()
        except Exception:
            return False

    if np:
        np.fill(_GREEN)
        np.write()
        end = time.ticks_add(time.ticks_ms(), 200)
        while time.ticks_diff(time.ticks_ms(), end) < 0:
            pass
        np.fill(_BLACK)
        np.write()

    return True
