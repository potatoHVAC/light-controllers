#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./deploy.sh <port>"
  echo ""
  echo "Installs the firmware in an A/B slot layout:"
  echo "  root:  boot.py, main.py, slots.py (trusted shims), active_slot, boot_count"
  echo "  /a /b: two firmware copies; either can be rolled back to"
  echo ""
  echo "A fresh device gets both slots seeded. On a device that already has"
  echo "firmware, the deploy writes only the UNPROVEN slot (same rule as OTA), so"
  echo "repeatedly deploying before a successful boot never clobbers a known-good"
  echo "slot — it keeps overwriting the untried one."
  echo ""
  echo "Arguments:"
  echo "  <port>  Serial port of the device (e.g. /dev/ttyUSB0)"
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

if [ -z "$1" ]; then
  echo "Usage: ./deploy.sh <port>  (e.g. ./deploy.sh /dev/ttyUSB0)"
  exit 1
fi

PORT=$1

# Firmware files inside each slot (NOT the root shims). Keep in sync with
# server/firmware.py OTA_FILES.
SLOT_FILES="app.py color.py button.py strip.py fixture.py storage.py controller.py \
themes.py mesh.py ota.py secrets.py bridge.py config.py auth.py log.py leader_link.py \
recovery.py device_config.py"

run_exec() { mpremote connect "$PORT" exec "$1"; }

echo "Stopping app (disarm watchdog) ..."
# Remove root main.py and reset: with no main.py the device reboots into a plain
# REPL with no watchdog, so the copy below has unlimited time. Also zero the boot
# counter so the deploy's own resets can't trip a rollback.
run_exec "$(cat <<'EOF'
import os
try: os.remove('main.py')
except OSError: pass
try:
    open('boot_count', 'w').write('0')
except OSError: pass
EOF
)"
mpremote connect "$PORT" reset
sleep 4

echo "Installing root shims (boot.py, slots.py) ..."
mpremote connect "$PORT" cp slots.py :slots.py + cp boot.py :boot.py

FW=$(python3 -c "import sys; sys.path.insert(0,'.'); from pathlib import Path; from server import firmware; print(firmware.current_version(Path('.')))")
if ! echo "$FW" | grep -qE '^[0-9a-f]{12}$'; then
  echo "Warning: could not compute firmware version — controller will appear outdated."
  FW=""
fi

# Decide which slot(s) to write. Fresh device (no app.py in either slot) → seed
# both. Otherwise write only the unproven slot (slots.update_target).
TARGET=$(run_exec "$(cat <<'EOF'
import os, slots
def has(s):
    try: os.stat(s + '/app.py'); return True
    except OSError: return False
for s in slots.SLOTS:
    try: os.mkdir(s)
    except OSError: pass
print('both' if (not has('a') and not has('b')) else slots.update_target())
EOF
)" | tr -d ' \r\n')

if [ "$TARGET" = "both" ]; then
  WRITE_SLOTS="a b"; ACTIVE="a"
  echo "Fresh device — seeding both slots."
else
  WRITE_SLOTS="$TARGET"; ACTIVE="$TARGET"
  echo "Writing unproven slot: /$TARGET"
fi

for SLOT in $WRITE_SLOTS; do
  echo "Installing slot /$SLOT ..."
  run_exec "$(cat <<EOF
import os
def rmtree(p):
    try:
        for f in os.listdir(p): rmtree(p+'/'+f)
        os.rmdir(p)
    except OSError:
        try: os.remove(p)
        except OSError: pass
rmtree('$SLOT')
os.mkdir('$SLOT'); os.mkdir('$SLOT/patterns')
EOF
)"

  CMD=(mpremote connect "$PORT")
  for f in $SLOT_FILES; do
    CMD+=(cp "$f" ":$SLOT/$f" +)
  done
  for f in patterns/*.py; do
    CMD+=(cp "$f" ":$SLOT/$f" +)
  done
  unset 'CMD[${#CMD[@]}-1]'
  "${CMD[@]}"

  # Record version and clear the proven flag (new firmware hasn't proven itself).
  run_exec "$(cat <<EOF
import slots
open('$SLOT/firmware_version', 'w').write('$FW')
slots.clear_proven('$SLOT')
EOF
)"
done

echo "Setting active slot = $ACTIVE ..."
run_exec "$(cat <<EOF
import slots
slots.set_active('$ACTIVE')
slots.reset_boot_count()
slots.clear_update_failed()
EOF
)"

# main.py LAST: until it exists no watchdog is armed, so a power cut mid-deploy
# leaves a safe (watchdog-free) device that the next deploy can recover.
echo "Installing main.py ..."
mpremote connect "$PORT" cp main.py :main.py

echo "Restarting device..."
mpremote connect "$PORT" reset

echo "Done. Active slot /$ACTIVE, firmware version: ${FW:-unknown}"