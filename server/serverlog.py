"""Bounded in-memory log shown on the admin page.

Each entry carries a source tag ('server' or 'mesh') so the two streams can
be displayed separately without maintaining two separate buffers."""
from datetime import datetime

MAX_ENTRIES = 300


class ServerLog:
    def __init__(self):
        self._entries = []

    def write(self, msg, level='info', source='server'):
        ts = datetime.now().strftime('%H:%M:%S')
        self._entries.append({'type': level, 'msg': f'[{ts}] {msg}', 'source': source})
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]
        print(f'[{ts}] {msg}')

    def entries(self, limit=200, source=None):
        entries = self._entries if source is None else [e for e in self._entries if e.get('source') == source]
        return entries[-limit:]
