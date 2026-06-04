import time
import network
import urequests
import socket
import os

import slots
from secrets import OTA_SSID, OTA_PASSWORD, BRIDGE_SECRET
from config import DISCOVERY_PORT, DISCOVERY_MSG, HTTP_PORT as OTA_PORT
from auth import verify as _verify_sig

UDP_PORT            = DISCOVERY_PORT
CHUNK_SIZE          = 512
WIFI_TIMEOUT_MS     = 5000
DISCOVER_TIMEOUT_MS = 1000

_ORANGE = (255, 80, 0)   # "writing flash, do not power off" — matches app.py
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
    """Check for an OTA server and download an update into the inactive slot.

    Files are downloaded into the slot this controller is NOT running from, and
    verified before the active-slot pointer is flipped to it. The running slot is
    never touched, so a power cut during the download just leaves the inactive
    slot half-written — the pointer still points at the working slot, so it boots
    normally and the garbage is overwritten on the next attempt.

    On success the pointer is flipped and the boot counter reset; the caller
    reboots into the new slot. If the new slot then crash-loops, boot.py flips
    the pointer back to this (still-intact) slot.

    WiFi is always shut down before returning so ESP-NOW initialises cleanly
    regardless of how this function exits.

    feed: optional watchdog-feed callback. The download outlasts the watchdog
    timeout, so it is fed through the connect/discovery/download loops.

    Returns True if a verified update is staged and the pointer flipped.
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

        # Download into an unproven slot (preferring the inactive one), so a run
        # of bad updates keeps overwriting the same untried slot and never
        # destroys the last known-good firmware. The running slot is only chosen
        # if it is itself the unproven one. Clear the target's proven flag (the
        # new firmware hasn't proven itself) and any prior failure record.
        target = slots.update_target()
        tdir   = slots.slot_dir(target)
        slots.clear_update_failed()
        slots.clear_proven(target)
        try:
            _rm_tree(tdir)        # discard whatever old version was in this slot
        except Exception:
            pass
        os.mkdir(tdir)

        # Orange "do not power off" marker for the whole flash-writing phase.
        if np:
            _danger(np)

        for f in files:
            if feed:
                feed()
            path = f['path']
            update_path = tdir + '/' + path
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
                _rm_tree(tdir)
                return False

        for f in files:
            try:
                if os.stat(tdir + '/' + f['path'])[6] != f['size']:
                    _rm_tree(tdir)
                    return False
            except Exception:
                _rm_tree(tdir)
                return False

        # Record the new slot's version, then flip the pointer and reset the boot
        # counter. The flip is the last step: until it succeeds the controller
        # still boots the old slot. After it, the caller reboots into the new one.
        try:
            with open(tdir + '/firmware_version', 'w') as vf:
                vf.write(manifest.get('version', ''))
        except Exception:
            pass

        slots.set_active(target)
        slots.reset_boot_count()

        if np:
            _flash_done(np)

        result = True
        return result

    finally:
        sta.active(False)
