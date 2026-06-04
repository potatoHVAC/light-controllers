"""pytest setup: install fake hardware modules before any project code imports,
patch the clock, and isolate per-test state (bus, clock, flash file)."""
import os
import sys
import types

_TESTS_DIR    = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)

# tests dir first so `import fakes.*` / `import harness` resolve; project root so
# `import mesh`, `controller`, etc. resolve.
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TESTS_DIR)

# Register the MicroPython-only modules as fakes under their real names, BEFORE
# any test imports controller code that does `import machine`, etc.
import fakes.machine, fakes.neopixel, fakes.network          # noqa: E401
import fakes.espnow, fakes.uhashlib, fakes.ubinascii          # noqa: E401

sys.modules['machine']   = fakes.machine
sys.modules['neopixel']  = fakes.neopixel
sys.modules['network']   = fakes.network
sys.modules['espnow']    = fakes.espnow
sys.modules['uhashlib']  = fakes.uhashlib
sys.modules['ubinascii'] = fakes.ubinascii
# urequests is only used at runtime inside ota.run(); a bare stub lets ota import.
sys.modules['urequests'] = types.ModuleType('urequests')

# Fake secrets: a superset of stdlib secrets plus the device credential names,
# so shadowing the stdlib module can't break anything that needs the real one.
import secrets as _real_secrets
_fake_secrets = types.ModuleType('secrets')
for _name in dir(_real_secrets):
    if not _name.startswith('__'):
        setattr(_fake_secrets, _name, getattr(_real_secrets, _name))
_fake_secrets.OTA_SSID      = 'TESTNET'
_fake_secrets.OTA_PASSWORD  = 'testpw'
_fake_secrets.BRIDGE_SECRET = 'test-bridge-secret'
sys.modules['secrets'] = _fake_secrets

import harness                                                # noqa: E402
harness.install()

import pytest                                                 # noqa: E402
from fakes.bus import BUS                                     # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    """Fresh bus + clock per test, and keep storage writes out of the repo."""
    import random
    random.seed(0)          # deterministic mesh nonces/jitter so sims don't flake
    BUS.reset()
    harness.reset_clock(0)
    import storage, device_config, slots
    storage._FILE = str(tmp_path / 'state.json')
    device_config._FILE = str(tmp_path / 'device_config.json')
    device_config._TMP  = str(tmp_path / 'device_config.json.tmp')
    slots.ROOT_DIR = str(tmp_path) + '/'
    yield
    BUS.reset()
