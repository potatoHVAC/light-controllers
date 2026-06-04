"""Bounded in-memory log shown on the admin page.

Server and mesh entries are kept in separate buffers so a noisy mesh
cannot evict server events."""
from datetime import datetime

MAX_ENTRIES = 300


class ServerLog:
    def __init__(self):
        self._server = []
        self._mesh   = []

    def write(self, msg, level='info', source='server'):
        ts = datetime.now().strftime('%H:%M:%S')
        entry = {'type': level, 'msg': f'[{ts}] {msg}'}
        buf = self._mesh if source == 'mesh' else self._server
        buf.append(entry)
        if len(buf) > MAX_ENTRIES:
            del buf[0]
        print(f'[{ts}] {msg}')

    def entries(self, limit=200, source=None):
        if source == 'mesh':
            return self._mesh[-limit:]
        if source == 'server':
            return self._server[-limit:]
        combined = sorted(self._server + self._mesh,
                          key=lambda e: e['msg'])   # timestamp prefix makes msg sortable
        return combined[-limit:]
