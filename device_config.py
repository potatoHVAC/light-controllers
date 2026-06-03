"""Per-controller persistent config (nickname, strip layout, personal defaults).

Stored on the device as device_config.json. It is NOT part of the firmware set,
so it survives OTA updates and is unique per controller. The server pushes it
via a set_config command; the controller saves it and reboots to apply (a strip
layout change needs a fresh setup).
"""
import json

_FILE = 'device_config.json'


def load():
    """Return the saved config dict, or {} if none."""
    try:
        with open(_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save(data):
    """Persist the config dict. Returns True on success."""
    try:
        with open(_FILE, 'w') as f:
            json.dump(data, f)
        return True
    except Exception:
        return False


def version(cfg=None):
    """The config version (0 if unconfigured) — reported to the server."""
    cfg = load() if cfg is None else cfg
    return cfg.get('version', 0)
