#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./server/run.sh [--local]"
  echo ""
  echo "Runs the Light Controllers server (control panel, admin, OTA, bridge)."
  echo "Control panel: http://localhost:8080/   Admin: http://localhost:8080/admin"
  echo ""
  echo "By default runs in Docker with host networking (so UDP discovery and the"
  echo "bridge reach the mesh). The project is mounted so firmware files are served"
  echo "and the SQLite db persists in server/lightrig.db."
  echo ""
  echo "Flags:"
  echo "  --local  Run directly with python3 -m server.app (no Docker)"
  echo "  -h       Show this help message"
  exit 0
fi

cd "$(dirname "$0")/.."

if [ "$1" = "--local" ]; then
  exec python3 -m server.app
fi

docker build -f server/Dockerfile -t lightrig-server . && \
  docker run --rm \
    --network host \
    -v "$(pwd):/firmware" \
    -e FIRMWARE_DIR=/firmware \
    -w /firmware \
    lightrig-server
