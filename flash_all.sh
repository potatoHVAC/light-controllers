#!/bin/bash
VERBOSE=false

for arg in "$@"; do
  case $arg in
    -h) echo "Usage: ./flash_all.sh <firmware.bin> [-v] [-h]"
        echo ""
        echo "Flashes MicroPython firmware to all ESP32 devices found on /dev/ttyUSB*."
        echo ""
        echo "Arguments:"
        echo "  <firmware.bin>  MicroPython firmware file to flash"
        echo ""
        echo "Flags:"
        echo "  -v  Verbose: flash sequentially with full output per device"
        echo "  -h  Show this help message"
        echo ""
        echo "Default behaviour (no flags): flash all devices in parallel."
        exit 0 ;;
    -v) VERBOSE=true ;;
  esac
done

if [ -z "$1" ] || [ "$1" = "-v" ]; then
  echo "Usage: ./flash_all.sh <firmware.bin>  (e.g. ./flash_all.sh ESP32_GENERIC-v1.28.0.bin)"
  exit 1
fi

FIRMWARE=$1

PORTS=(/dev/ttyUSB*)

if [ ${#PORTS[@]} -eq 0 ] || [ ! -e "${PORTS[0]}" ]; then
  echo "No devices found on /dev/ttyUSB*"
  exit 1
fi

if $VERBOSE; then
  for PORT in "${PORTS[@]}"; do
    echo "=== Flashing $PORT ==="
    ./flash_firmware.sh "$PORT" "$FIRMWARE"
  done
else
  for PORT in "${PORTS[@]}"; do
    ./flash_firmware.sh "$PORT" "$FIRMWARE" &
  done
  wait
  echo "All devices flashed."
fi
