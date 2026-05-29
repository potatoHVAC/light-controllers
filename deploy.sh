#!/bin/bash
if [ -z "$1" ]; then
  echo "Usage: ./deploy.sh <port>  (e.g. ./deploy.sh /dev/ttyUSB0)"
  exit 1
fi

PORT=$1

mpremote connect "$PORT" \
  cp addressable_main.py :main.py + \
  cp color.py button.py strip.py fixture.py storage.py controller.py themes.py : + \
  cp -r patterns/ :patterns/

echo "Done."
