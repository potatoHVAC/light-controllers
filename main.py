# main.py — root shim (part of the trusted base; updated only by wired deploy).
#
# boot.py has already put the active slot on sys.path. Arm the watchdog FIRST so
# a hang during the slot's import (top-level module code that never returns) is
# caught as a watchdog reset — which boot.py counts — instead of leaving a frozen
# unit. Then run the slot's app. The app re-acquires the same watchdog and feeds
# it from its loop. A failure here means the slot couldn't import/start (corrupt
# firmware); we reset, which re-enters boot.py and counts another fault. After
# enough faults boot.py falls back to the other slot.
try:
    from machine import WDT
    WDT(timeout=8000)   # must match app.WDT_TIMEOUT_MS; app re-acquires + feeds it
except Exception:
    pass

try:
    import app
    app.run()
except Exception:
    # Slot couldn't import/start (corrupt firmware). Flag the fault so boot.py
    # counts it toward a rollback, then reset back into boot.py.
    try:
        import slots
        slots.set_fault()
    except Exception:
        pass

import machine
machine.reset()