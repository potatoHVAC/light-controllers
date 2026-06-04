"""A/B slot management: pointer, boot counter, proven flag, update targeting,
and rollback. ROOT_DIR is pointed at a tmp dir by conftest's _isolate fixture."""
import os

import slots


def _mkslots():
    """Create empty /a and /b dirs under the test ROOT_DIR."""
    for s in slots.SLOTS:
        os.mkdir(slots.slot_dir(s))


def _write_version(slot, v):
    with open(slots.slot_dir(slot) + '/firmware_version', 'w') as f:
        f.write(v)


def test_active_defaults_to_first_slot():
    assert slots.active() == 'a'
    slots.set_active('b')
    assert slots.active() == 'b'
    assert slots.other('b') == 'a'


def test_boot_count_increments_and_resets():
    assert slots.boot_count() == 0
    assert slots.incr_boot_count() == 1
    assert slots.incr_boot_count() == 2
    slots.reset_boot_count()
    assert slots.boot_count() == 0


def test_proven_flag():
    assert slots.is_proven('a') is False
    slots.mark_proven('a')
    assert slots.is_proven('a') is True
    slots.clear_proven('a')
    assert slots.is_proven('a') is False


def test_update_target_prefers_unproven_slot():
    # a proven, b not → updates must hit b, regardless of which is active
    slots.mark_proven('a')
    slots.set_active('a')
    assert slots.update_target() == 'b'
    slots.set_active('b')                 # even while running b, preserve proven a
    assert slots.update_target() == 'b'


def test_update_target_both_proven_uses_inactive():
    slots.mark_proven('a')
    slots.mark_proven('b')
    slots.set_active('a')
    assert slots.update_target() == 'b'
    slots.set_active('b')
    assert slots.update_target() == 'a'


def test_update_target_neither_proven_uses_inactive():
    slots.set_active('a')
    assert slots.update_target() == 'b'


def test_revert_flips_pointer_resets_count_and_flags():
    _mkslots()
    _write_version('a', 'aaaaaaaaaaaa')
    slots.set_active('a')
    slots.set_boot_count(5)
    now_active = slots.revert()
    assert now_active == 'b'
    assert slots.active() == 'b'
    assert slots.boot_count() == 0
    assert slots.update_failed() == ('a', 'aaaaaaaaaaaa')


def test_revert_always_flips_even_if_both_failed():
    # No proven slots, both "bad": revert must still flip so we keep trying.
    slots.set_active('a')
    assert slots.revert() == 'b'
    assert slots.revert() == 'a'          # flips back — never refuses to boot


def test_bad_update_repeat_keeps_hitting_same_slot():
    # a is the known-good proven slot; repeated bad updates must always target b.
    slots.mark_proven('a')
    slots.set_active('a')
    for _ in range(3):
        target = slots.update_target()
        assert target == 'b'              # never clobbers proven a
        slots.clear_proven(target)        # writing new firmware clears proven
        slots.set_active(target)          # ota flips to the new slot
        # b boots badly → boot.py reverts back to a
        slots.revert()
        assert slots.active() == 'a'


def test_fault_flag_set_and_taken_once():
    assert slots.take_fault() is False
    slots.set_fault()
    assert slots.take_fault() is True
    assert slots.take_fault() is False     # cleared after being read


def test_version_reads_slot_file():
    _mkslots()
    _write_version('b', 'deadbeef0000')
    assert slots.version('b') == 'deadbeef0000'
    assert slots.version('a') is None