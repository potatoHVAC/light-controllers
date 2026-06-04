#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./deploy.sh <port>"
  echo ""
  echo "Wipes the device, copies all firmware files, and restarts the ESP32."
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

echo "Wiping device..."
# Delete everything except boot.py. Removing main.py is the key step: the
# hardware watchdog is only started inside main.py, so once it is gone the
# device reboots into a plain REPL with no watchdog running — giving the file
# copy below unlimited time. The delete itself is fast (well under the 8s
# watchdog window), so it completes even while the old main.py's watchdog is
# still ticking.
mpremote connect "$PORT" exec "$(cat <<'EOF'
import os

def rmtree(path):
    try:
        for f in os.listdir(path):
            rmtree(path + '/' + f)
        os.rmdir(path)
    except OSError:
        os.remove(path)

keep = {'boot.py'}
for f in os.listdir('/'):
    if f not in keep:
        try: rmtree('/' + f)
        except: pass
EOF
)"

# Hard reset with the dedicated subcommand (not machine.reset() inside exec,
# which makes mpremote follow the reboot and hang on the device's REPL). This
# resets and disconnects cleanly so the watchdog is gone before we copy.
mpremote connect "$PORT" reset

# Wait for the reboot: ~boot.py's 2s sleep plus reset/enumeration margin.
sleep 4

echo "Copying files..."
mpremote connect "$PORT" \
  cp boot.py :boot.py + \
  cp main.py :main.py + \
  cp color.py button.py strip.py fixture.py storage.py controller.py themes.py mesh.py ota.py secrets.py bridge.py config.py auth.py log.py leader_link.py recovery.py device_config.py :

mpremote connect "$PORT" exec "import os; os.mkdir('patterns')"

CMD=(mpremote connect "$PORT")
for f in patterns/*.py; do
  CMD+=(cp "$f" ":$f" +)
done
unset 'CMD[${#CMD[@]}-1]'
"${CMD[@]}"

# Stamp the firmware version so the controller reports it (matches what an OTA
# update would write), letting the admin page tell who is up to date.
FW=$(python3 -c "import sys; sys.path.insert(0,'.'); from pathlib import Path; from server import firmware; print(firmware.current_version(Path('.')))")
if echo "$FW" | grep -qE '^[0-9a-f]{12}$'; then
  echo "Stamping firmware version $FW..."
  mpremote connect "$PORT" exec "open('firmware_version','w').write('$FW')"
else
  echo "Warning: could not compute firmware version — controller will appear outdated until redeployed."
  echo "  Make sure you are running deploy.sh from the project root."
fi

echo "Restarting device..."
mpremote connect "$PORT" reset

echo "Done."
