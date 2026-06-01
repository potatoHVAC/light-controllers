#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./hotspot.sh [interface]"
  echo ""
  echo "Starts a WiFi hotspot for controller updates and show control."
  echo "Credentials are read from secrets.py in the project root."
  echo "Not needed when using a phone or tablet as the hotspot."
  echo ""
  echo "Arguments:"
  echo "  [interface]  WiFi interface to use (Linux only, default: wlan0)"
  echo "               Find yours with: ip link show"
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

if [ ! -f secrets.py ]; then
  echo "Error: secrets.py not found. Copy secrets.py.example to secrets.py and set your credentials."
  exit 1
fi

SSID=$(python3 -c "from secrets import OTA_SSID; print(OTA_SSID)")
PASSWORD=$(python3 -c "from secrets import OTA_PASSWORD; print(OTA_PASSWORD)")

OS=$(uname)

if [ "$OS" = "Darwin" ]; then
  echo "Starting hotspot on macOS..."
  echo "SSID:     $SSID"
  echo ""
  echo "Note: macOS does not support command-line hotspot creation."
  echo "Enable Internet Sharing manually in System Settings → General → Sharing,"
  echo "then set the network name to: $SSID"
  exit 0
fi

# Linux (nmcli)
IFACE="${1:-wlan0}"
echo "Starting hotspot on $IFACE..."
echo "SSID:     $SSID"
echo ""

nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWORD" band bg channel 1
