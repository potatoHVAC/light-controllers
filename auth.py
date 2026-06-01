"""HMAC-SHA256 signing and verification for bridge commands.

Commands are signed as: <json_bytes>|<hmac_hex>
The controller verifies over the raw JSON bytes before parsing, which avoids
any JSON key-ordering inconsistency between Python 3 and MicroPython.
"""
import uhashlib
import ubinascii


def _hmac_sha256(key, msg):
    if isinstance(key, str):
        key = key.encode()
    if isinstance(msg, str):
        msg = msg.encode()
    block_size = 64
    if len(key) > block_size:
        key = uhashlib.sha256(key).digest()
    key = key + b'\x00' * (block_size - len(key))
    o_key = bytearray(b ^ 0x5C for b in key)
    i_key = bytearray(b ^ 0x36 for b in key)
    inner = uhashlib.sha256(bytes(i_key) + msg).digest()
    return uhashlib.sha256(bytes(o_key) + inner).digest()


def sign(key, payload_bytes):
    """Return hex HMAC-SHA256 of payload_bytes using key."""
    return ubinascii.hexlify(_hmac_sha256(key, payload_bytes)).decode()


def verify(key, payload_bytes, sig_hex):
    """Return True if sig_hex is a valid HMAC-SHA256 of payload_bytes.
    Uses constant-time comparison to prevent timing attacks."""
    expected = sign(key, payload_bytes)
    if len(expected) != len(sig_hex):
        return False
    result = 0
    for a, b in zip(expected, sig_hex):
        result |= ord(a) ^ ord(b)
    return result == 0
