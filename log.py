"""On-device circular log buffer with mesh broadcast.

Log entries are stored locally (accessible via serial) and broadcast as
ESP-NOW packets so the bridge can forward them to the server's debug page.

Usage:
    import log
    log.set_mesh(mesh)          # call once after Mesh() is created
    log.write('mesh', 'leader elected')
    log.write('ota', 'download failed', level='warn')
    log.write('ctrl', 'unknown theme received', level='error')
"""

import time

MAX_ENTRIES = 50
_entries = []
_mesh = None


def set_mesh(mesh):
    """Attach the mesh so log entries are broadcast to all controllers."""
    global _mesh
    _mesh = mesh


def write(source, msg, level='info'):
    """Append a log entry to the local buffer and broadcast via mesh."""
    entry = {
        'type': 'log',
        'src':  source,
        'lvl':  level,
        'msg':  msg,
        't':    time.ticks_ms(),
    }
    _entries.append(entry)
    if len(_entries) > MAX_ENTRIES:
        _entries.pop(0)
    if _mesh:
        _mesh.send_log(source, msg, level)


def get_entries():
    return list(_entries)
