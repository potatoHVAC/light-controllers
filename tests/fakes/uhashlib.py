"""Fake uhashlib → CPython hashlib. Lets auth.py run unchanged off-device."""
from hashlib import sha256  # noqa: F401
