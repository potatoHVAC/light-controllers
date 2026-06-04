#!/bin/bash
VERBOSE=false

for arg in "$@"; do
  case $arg in
    -h) echo "Usage: ./bootstrap_all.sh <firmware.bin> [-v] [-h]"
        echo ""
        echo "Flashes MicroPython firmware then deploys code to all ESP32 devices"
        echo "found on /dev/ttyUSB*."
        echo ""
        echo "Arguments:"
        echo "  <firmware.bin>  MicroPython firmware file to flash"
        echo ""
        echo "Flags:"
        echo "  -v  Verbose: run sequentially with full output per device"
        echo "  -h  Show this help message"
        echo ""
        echo "Default behaviour (no flags): flash and deploy all devices in parallel."
        exit 0 ;;
    -v) VERBOSE=true ;;
  esac
done

if [ -z "$1" ] || [ "$1" = "-v" ]; then
  echo "Usage: ./bootstrap_all.sh <firmware.bin>  (e.g. ./bootstrap_all.sh ESP32_GENERIC-v1.28.0.bin)"
  exit 1
fi

FIRMWARE=$1
VERBOSE_FLAG=""
$VERBOSE && VERBOSE_FLAG="-v"

echo "=== Flashing firmware ==="
./flash_all.sh "$FIRMWARE" $VERBOSE_FLAG || exit 1

echo ""
echo "Waiting for devices to complete first boot..."
sleep 5

echo "=== Deploying code ==="
./deploy_all.sh $VERBOSE_FLAG
