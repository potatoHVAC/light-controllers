#!/bin/bash
VERBOSE=false

for arg in "$@"; do
  case $arg in
    -h) echo "Usage: ./deploy_all.sh [-v] [-h]"
        echo ""
        echo "Deploys firmware to all ESP32 devices found on /dev/ttyUSB*."
        echo ""
        echo "Flags:"
        echo "  -v  Verbose: deploy sequentially with full output per device"
        echo "  -h  Show this help message"
        echo ""
        echo "Default behaviour (no flags): deploy to all devices in parallel."
        exit 0 ;;
    -v) VERBOSE=true ;;
  esac
done

PORTS=(/dev/ttyUSB*)

if [ ${#PORTS[@]} -eq 0 ] || [ ! -e "${PORTS[0]}" ]; then
  echo "No devices found on /dev/ttyUSB*"
  exit 1
fi

if $VERBOSE; then
  for PORT in "${PORTS[@]}"; do
    echo "=== Deploying to $PORT ==="
    ./deploy.sh "$PORT"
  done
else
  for PORT in "${PORTS[@]}"; do
    ./deploy.sh "$PORT" &
  done
  wait
  echo "All deployments complete."
fi
