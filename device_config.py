"""Per-controller persistent config (nickname, strip layout, personal defaults).

Stored on the device as device_config.json. It is NOT part of the firmware set,
so it survives OTA updates and is unique per controller. The server pushes it
via a set_config command; the controller saves it and reboots to apply (a strip
layout change needs a fresh setup).
"""
import json
import os

_FILE = 'device_config.json'
_TMP  = _FILE + '.tmp'


def load():
    """Return the saved config dict, or {} if none."""
    try:
        with open(_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save(data):
    """Persist the config dict atomically. Returns True on success.

    Writes a temp file then renames over the target — os.rename is atomic on
    littlefs, so a power loss mid-write leaves the previous config intact rather
    than a half-written (and unparseable) file."""
    try:
        with open(_TMP, 'w') as f:
            json.dump(data, f)
        os.rename(_TMP, _FILE)
        return True
    except Exception:
        try:
            os.remove(_TMP)
        except Exception:
            pass
        return False


def version(cfg=None):
    """The config version (0 if unconfigured) — reported to the server."""
    cfg = load() if cfg is None else cfg
    return cfg.get('version', 0)
