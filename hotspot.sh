#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./hotspot.sh [interface]"
  echo ""
  echo "Starts a WiFi hotspot for OTA controller updates."
  echo "Credentials are read from .env (OTA_SSID / OTA_PASSWORD)."
  echo ""
  echo "Arguments:"
  echo "  [interface]  WiFi interface to use (default: wlan0)"
  echo "               Find yours with: ip link show"
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

if [ ! -f .env ]; then
  echo "Error: .env file not found. Copy .env.example to .env and set your credentials."
  exit 1
fi
source .env

IFACE="${1:-wlan0}"
SSID="$OTA_SSID"
PASSWORD="$OTA_PASSWORD"

echo "Starting hotspot on $IFACE..."
echo "SSID:     $SSID"
echo "Password: $PASSWORD"
echo ""

nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWORD"
