#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./server/run.sh"
  echo ""
  echo "Builds and runs the OTA and show control server in Docker."
  echo "Firmware files are mounted from the project root."
  echo "Open http://localhost:8080 for OTA status."
  echo "Open http://localhost:8080/panel for the show control panel."
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

cd "$(dirname "$0")/.."

docker build -f server/Dockerfile -t lightrig-ota . && \
  docker run --rm \
    -p 8080:8080 \
    -p 5001:5001/udp \
    -v "$(pwd):/firmware" \
    -e FIRMWARE_DIR=/firmware \
    lightrig-ota
