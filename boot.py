# boot.py — root shim (part of the trusted base; updated only by wired deploy).
#
# Crash-recovery supervisor. Counts only resets caused by a firmware FAULT — a
# watchdog fire or a machine.reset() from the fault handler. A user power-cycle
# (power-on reset) or a deep-sleep wake is NOT a fault and is never counted, so
# rapidly power-cycling a healthy unit can't falsely mark it broken. The active
# slot's app resets the counter once it has run stably. If a slot keeps faulting
# without ever proving stable, fall back to the other slot and flag the failed
# update for the admin page.
#
# Hangs are caught too: main.py arms the watchdog before importing the slot, so a
# hang anywhere produces a watchdog reset — which counts here — rather than
# relying on the user to power-cycle.
#
# Everything is wrapped so boot.py can never itself be the thing that fails.
import sys
import time

try:
    import slots
except Exception:
    slots = None

if slots is not None:
    try:
        import machine
        # A boot counts as failed only if the firmware faulted: either a fault
        # handler flagged it (set_fault before reset), or the watchdog fired (a
        # hang — can't run a handler). A clean user power-cycle is neither, so it
        # never counts. reset_cause is consulted only for the watchdog, whose
        # value is well defined; we don't guess what machine.reset() reports.
        faulted = slots.take_fault()
        try:
            faulted = faulted or (machine.reset_cause() == machine.WDT_RESET)
        except Exception:
            pass
        if faulted and slots.incr_boot_count() > slots.THRESHOLD:
            slots.revert()           # always flip — never refuse to boot
            machine.reset()          # reboot into the fallback slot
    except Exception:
        pass

    try:
        sys.path.insert(0, slots.slot_dir(slots.active()))
    except Exception:
        pass

time.sleep_ms(2000)   # boot settle / leaves a window to Ctrl-C into the REPL