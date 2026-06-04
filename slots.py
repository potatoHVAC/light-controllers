"""A/B firmware slots and crash-recovery bookkeeping.

The device keeps two complete firmware copies, /a and /b. A pointer file picks
which one boots. An OTA writes the *inactive* slot and flips the pointer — never
the running slot — so a bad download can't touch what's working, and a bad
update rolls back by flipping the pointer back. At most two copies ever exist;
nothing is staged or deleted from under the running firmware.

Files at the filesystem root (shared across both slots, never themselves A/B'd):
    active_slot      'a' or 'b' — which slot boots
    boot_count       consecutive boots that haven't yet proven stable
    update_failed     "<slot>:<version>" when a slot was rolled back (admin flag)
    slot_broken_<x>  marker that slot <x> is known-bad (don't boot it)

The root shims boot.py / main.py / slots.py select and run the active slot. They
are the small trusted base, updated only by a wired deploy, never by OTA.

Paths hang off ROOT_DIR so the logic is testable off-device.
"""
import os

ROOT_DIR  = '/'
SLOTS     = ('a', 'b')
THRESHOLD = 3        # failed boots before falling back to the other slot


def _p(name):
    return ROOT_DIR + name


def slot_dir(slot):
    return ROOT_DIR + slot


def _read(name):
    try:
        with open(_p(name)) as f:
            return f.read().strip()
    except Exception:
        return None


def _write(name, data):
    """Atomic write via temp+rename (rename is atomic on littlefs)."""
    p = _p(name)
    try:
        with open(p + '.tmp', 'w') as f:
            f.write(data)
        os.rename(p + '.tmp', p)
    except Exception:
        try:
            with open(p, 'w') as f:
                f.write(data)
        except Exception:
            pass


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(name):
    try:
        os.remove(_p(name))
    except OSError:
        pass


# ── active slot ───────────────────────────────────────────────────────────────

def active():
    s = _read('active_slot')
    return s if s in SLOTS else SLOTS[0]


def other(slot):
    return SLOTS[1] if slot == SLOTS[0] else SLOTS[0]


def set_active(slot):
    _write('active_slot', slot)


# ── boot counter ──────────────────────────────────────────────────────────────

def boot_count():
    try:
        return int(_read('boot_count') or 0)
    except Exception:
        return 0


def set_boot_count(n):
    _write('boot_count', str(n))


def reset_boot_count():
    set_boot_count(0)


def incr_boot_count():
    n = boot_count() + 1
    set_boot_count(n)
    return n


# ── proven flag (has the slot ever booted to a healthy state?) ────────────────
#
# A slot is "proven" once its firmware has booted and run stably. Writing new
# firmware to a slot clears it (the new code hasn't proven itself). Updates
# always target an UNPROVEN slot so a run of bad firmwares keeps overwriting the
# same untried slot and never destroys the last known-good one.

def mark_proven(slot):
    _write('slot_proven_' + slot, '1')


def is_proven(slot):
    return _exists(_p('slot_proven_' + slot))


def clear_proven(slot):
    _remove('slot_proven_' + slot)


def update_target():
    """The slot an update should be written to: an unproven slot if there is
    one (so bad updates keep hitting the same untried slot), otherwise the
    inactive slot (so two good versions ping-pong)."""
    a, b = SLOTS
    a_ok, b_ok = is_proven(a), is_proven(b)
    if a_ok and not b_ok:
        return b
    if b_ok and not a_ok:
        return a
    return other(active())     # both proven, or neither: write the inactive one


# ── fault flag (set by the fault handlers just before a reset) ────────────────
#
# boot.py counts a boot as failed if EITHER this flag is set (the firmware reset
# itself from a fault handler) OR the reset cause was the watchdog (a hang, which
# can't run a handler). A clean user power-cycle leaves no flag and isn't a
# watchdog reset, so it never counts — rapidly cycling a healthy unit is safe.

def set_fault():
    _write('fault_pending', '1')


def take_fault():
    """Return True if the last boot flagged a fault, clearing the flag."""
    if _exists(_p('fault_pending')):
        _remove('fault_pending')
        return True
    return False


# ── failed-update flag (admin) ────────────────────────────────────────────────

def set_update_failed(slot, version):
    _write('update_failed', slot + ':' + (version or ''))


def update_failed():
    """Return (slot, version) of the last rolled-back update, or None."""
    raw = _read('update_failed')
    if not raw or ':' not in raw:
        return None
    slot, _, version = raw.partition(':')
    return (slot, version)


def clear_update_failed():
    _remove('update_failed')


# ── slot version ──────────────────────────────────────────────────────────────

def version(slot):
    try:
        with open(slot_dir(slot) + '/firmware_version') as f:
            return f.read().strip() or None
    except Exception:
        return None


# ── recovery ──────────────────────────────────────────────────────────────────

def revert():
    """Fall back from the active slot to the other one: record the failed update
    for the admin page, flip the pointer, and clear the boot counter (giving the
    fallback a fresh set of attempts). Always flips — even to a slot that has
    also failed — so the controller never refuses to boot; if both slots are bad
    it keeps alternating and retrying. Returns the slot now active."""
    cur = active()
    nxt = other(cur)
    set_update_failed(cur, version(cur))
    set_active(nxt)
    reset_boot_count()
    return nxt