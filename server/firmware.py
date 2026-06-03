"""Firmware manifest and version hashing.

The version is a hash over the firmware source files, so the server can tell at
a glance which controllers are running current firmware. Credentials
(`secrets.py`) and a controller's personal config (`device_config.json`, never
part of the firmware set) are excluded — a credential rotation or a per-member
config change is not a firmware change.

OTA_FILES mirrors deploy.sh. Keep both in sync when adding files.
"""
import hashlib

OTA_FILES = [
    'boot.py', 'main.py', 'controller.py', 'mesh.py', 'bridge.py',
    'auth.py', 'log.py', 'leader_link.py', 'recovery.py',
    'ota.py', 'color.py', 'button.py', 'strip.py',
    'fixture.py', 'storage.py', 'themes.py', 'secrets.py', 'config.py',
    'device_config.py',
    'patterns/__init__.py', 'patterns/base.py', 'patterns/bounce_pulse.py',
    'patterns/breathe.py', 'patterns/breathe_center.py', 'patterns/center_meet.py',
    'patterns/dna_pulse.py', 'patterns/firefly.py', 'patterns/flash_rb.py',
    'patterns/glitter.py', 'patterns/launch.py', 'patterns/rainbow.py',
    'patterns/rainbow_flash.py', 'patterns/resonance.py', 'patterns/solid.py',
    'patterns/spinner.py',
]

# Excluded from the version hash (credentials, not behaviour).
_VERSION_EXCLUDE = {'secrets.py'}

VERSION_LEN = 12   # short hex prefix used as the human-facing version id


def manifest(root, files=OTA_FILES):
    """Return {'files': [{'path','size'}], 'version': <hash>} for present files.
    `root` is a pathlib.Path to the firmware source tree."""
    entries = []
    for path in files:
        full = root / path
        if full.exists():
            entries.append({'path': path, 'size': full.stat().st_size})
    return {'files': entries, 'version': current_version(root, files)}


def current_version(root, files=OTA_FILES):
    """SHA-256 over the (path, content) of every present firmware file except
    the excluded ones. Returns a short hex string.

    Files are always processed in sorted order so the hash is stable regardless
    of the order entries appear in OTA_FILES."""
    h = hashlib.sha256()
    for path in sorted(files):
        if path in _VERSION_EXCLUDE:
            continue
        full = root / path
        if not full.exists():
            continue
        h.update(path.encode())
        h.update(b'\0')
        h.update(full.read_bytes())
        h.update(b'\0')
    return h.hexdigest()[:VERSION_LEN]


def version_detail(root, files=OTA_FILES):
    """Return a breakdown of what went into the current version hash.

    Useful for debugging why a controller's reported version doesn't match the
    server. Returns {'version': str, 'files': [{'path', 'sha256', 'excluded',
    'missing'}]} in the sorted order the hash uses."""
    overall = hashlib.sha256()
    entries = []
    for path in sorted(files):
        excluded = path in _VERSION_EXCLUDE
        full = root / path
        missing = not full.exists()
        file_hash = None
        if not excluded and not missing:
            content = full.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()[:VERSION_LEN]
            overall.update(path.encode())
            overall.update(b'\0')
            overall.update(content)
            overall.update(b'\0')
        entries.append({'path': path, 'sha256': file_hash,
                        'excluded': excluded, 'missing': missing})
    return {'version': overall.hexdigest()[:VERSION_LEN], 'files': entries}
