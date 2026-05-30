#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./flash_firmware.sh <port> <firmware.bin>"
  echo ""
  echo "Erases the ESP32 flash and writes a fresh MicroPython firmware image."
  echo ""
  echo "Arguments:"
  echo "  <port>          Serial port of the device (e.g. /dev/ttyUSB0)"
  echo "  <firmware.bin>  MicroPython firmware file to flash"
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: ./flash_firmware.sh <port> <firmware.bin>"
  echo "  e.g. ./flash_firmware.sh /dev/ttyUSB0 ESP32_GENERIC-20241129-v1.24.1.bin"
  exit 1
fi

PORT=$1
FIRMWARE=$2

esptool --chip esp32 --port "$PORT" erase-flash
esptool --chip esp32 --port "$PORT" write-flash -z 0x1000 "$FIRMWARE"
