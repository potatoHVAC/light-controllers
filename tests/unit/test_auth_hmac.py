"""Cross-runtime HMAC contract: auth.py (device, hand-rolled HMAC over uhashlib)
must produce byte-identical output to CPython's hmac module (the server). If
these ever disagree, every signed bridge command silently fails."""
import hashlib
import hmac

import auth


def _stdlib(key, payload):
    return hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def test_matches_stdlib_short_key():
    payload = b'{"type":"change","theme":"red"}'
    assert auth.sign('short', payload) == _stdlib('short', payload)


def test_matches_stdlib_block_boundary_keys():
    # Keys around the 64-byte block size exercise both HMAC branches:
    # <64 zero-pads, >64 gets hashed first.
    for n in (1, 63, 64, 65, 200):
        key = 'k' * n
        payload = b'payload-bytes'
        assert auth.sign(key, payload) == _stdlib(key, payload), f'key len {n}'


def test_verify_accepts_valid_signature():
    payload = b'{"seq":1,"type":"dim","dim":0.5}'
    sig = auth.sign('secret', payload)
    assert auth.verify('secret', payload, sig)


def test_verify_rejects_tampered_payload():
    payload = b'{"seq":1,"type":"dim","dim":0.5}'
    sig = auth.sign('secret', payload)
    assert not auth.verify('secret', payload + b' ', sig)


def test_verify_rejects_wrong_key():
    payload = b'data'
    sig = auth.sign('secret', payload)
    assert not auth.verify('other', payload, sig)


def test_verify_rejects_wrong_length_signature():
    assert not auth.verify('secret', b'data', 'deadbeef')
