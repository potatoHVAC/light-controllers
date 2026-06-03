#!/usr/bin/env python3
"""
Auto-reload server for Light Controllers.

Watches the server package and shared config/secrets, restarting the server on
any change. Run from the project root:

    python3 server/watch.py
"""

import glob
import os
import sys
import time
import subprocess


def watch_files():
    files = ['config.py', 'secrets.py']
    files += glob.glob('server/*.py')
    files += glob.glob('server/static/*')
    return files


def get_mtimes():
    mtimes = {}
    for f in watch_files():
        try:
            mtimes[f] = os.path.getmtime(f)
        except FileNotFoundError:
            mtimes[f] = 0
    return mtimes


def start_server():
    return subprocess.Popen([sys.executable, '-m', 'server.app'])


def main():
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        sys.exit(0)

    proc = start_server()
    mtimes = get_mtimes()
    print('Server started. Watching for changes (Ctrl+C to stop)...')

    try:
        while True:
            time.sleep(1)
            if proc.poll() is not None:
                print('Server exited — restarting...')
                proc = start_server()
                continue
            new_mtimes = get_mtimes()
            changed = [f for f in new_mtimes if new_mtimes[f] != mtimes.get(f)]
            if changed:
                print(f'Changed: {", ".join(changed)} — restarting...')
                proc.terminate(); proc.wait()
                proc = start_server()
                mtimes = new_mtimes
    except KeyboardInterrupt:
        print('\nStopping server...')
        proc.terminate(); proc.wait()


if __name__ == '__main__':
    main()
