"""OTA watchdog feeding: the download outlasts the watchdog timeout, so run()
must feed it through its wait loops. Also the completed-download flash exists."""
import types

import harness
import ota


def test_discover_server_feeds_watchdog(monkeypatch):
    fed = []

    class _Sock:
        def setblocking(self, v): pass
        def bind(self, a): pass
        def close(self): pass
        def recvfrom(self, n): raise OSError('empty')   # never receives

    fake_socket = types.ModuleType('socket')
    fake_socket.AF_INET    = 2
    fake_socket.SOCK_DGRAM = 2
    fake_socket.socket     = lambda *a, **k: _Sock()

    monkeypatch.setattr(ota, 'socket', fake_socket)
    monkeypatch.setattr(ota, 'DISCOVER_TIMEOUT_MS', 50)

    # The feed advances the (frozen) test clock so the wait loop terminates —
    # which also proves the feed is actually being called during the wait.
    def feed():
        fed.append(1)
        harness.advance(10)

    assert ota._discover_server(feed=feed) is None
    assert len(fed) > 0


def test_run_accepts_feed_kwarg():
    # Signature contract: main.py calls ota.run(np=..., feed=...).
    import inspect
    params = inspect.signature(ota.run).parameters
    assert 'feed' in params


def test_done_flash_helper_present():
    assert hasattr(ota, '_flash_done')
