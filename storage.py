import json

_FILE = 'state.json'


def load(defaults):
    """Load saved state from flash. Missing keys fall back to defaults."""
    try:
        with open(_FILE) as f:
            data = json.load(f)
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(defaults)


def save(data):
    """Write state to flash. Called deferred — not on every button press."""
    try:
        with open(_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        try:
            import log
            log.write('storage', 'save failed: ' + str(e), level='warn')
        except Exception:
            pass
