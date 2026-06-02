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

echo "Copying files..."
mpremote connect "$PORT" \
  cp boot.py :boot.py + \
  cp main.py :main.py + \
  cp color.py button.py strip.py fixture.py storage.py controller.py themes.py mesh.py ota.py secrets.py bridge.py config.py auth.py log.py :

mpremote connect "$PORT" exec "import os; os.mkdir('patterns')"

CMD=(mpremote connect "$PORT")
for f in patterns/*.py; do
  CMD+=(cp "$f" ":$f" +)
done
unset 'CMD[${#CMD[@]}-1]'
"${CMD[@]}"

echo "Restarting device..."
mpremote connect "$PORT" reset

echo "Done."
