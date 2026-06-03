"""Bounded in-memory log shown on the control/admin pages."""
from datetime import datetime

MAX_ENTRIES = 300


class ServerLog:
    def __init__(self):
        self._entries = []

    def write(self, msg, level='info'):
        ts = datetime.now().strftime('%H:%M:%S')
        self._entries.append({'type': level, 'msg': f'[{ts}] {msg}'})
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]
        print(f'[{ts}] {msg}')

    def entries(self, limit=200):
        return self._entries[-limit:]
