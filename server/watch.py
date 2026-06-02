#!/usr/bin/env python3
"""
Auto-reload server for Light Controllers.

Watches server/serve.py and shared config files for changes and restarts
the server automatically. Run from the project root.

Usage:
    python3 server/watch.py
"""

import os
import sys
import time
import signal
import subprocess

WATCH_FILES = [
    'server/serve.py',
    'config.py',
    'secrets.py',
    'auth.py',
]

CHECK_INTERVAL = 1  # seconds between mtime checks


def get_mtimes():
    mtimes = {}
    for f in WATCH_FILES:
        try:
            mtimes[f] = os.path.getmtime(f)
        except FileNotFoundError:
            mtimes[f] = 0
    return mtimes


def start_server():
    return subprocess.Popen([sys.executable, 'server/serve.py'])


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        sys.exit(0)

    proc = start_server()
    mtimes = get_mtimes()
    print('Server started. Watching for changes (Ctrl+C to stop)...')

    try:
        while True:
            time.sleep(CHECK_INTERVAL)

            # Check if server process died unexpectedly
            if proc.poll() is not None:
                print('Server exited — restarting...')
                proc = start_server()
                continue

            new_mtimes = get_mtimes()
            changed = [f for f in WATCH_FILES if new_mtimes[f] != mtimes[f]]
            if changed:
                print(f'Changed: {", ".join(changed)} — restarting server...')
                proc.terminate()
                proc.wait()
                proc = start_server()
                mtimes = new_mtimes

    except KeyboardInterrupt:
        print('\nStopping server...')
        proc.terminate()
        proc.wait()


if __name__ == '__main__':
    main()
