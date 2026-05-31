#!/bin/bash
if [ "$1" = "-h" ]; then
  echo "Usage: ./hotspot.sh [interface]"
  echo ""
  echo "Starts a WiFi hotspot for OTA controller updates."
  echo "SSID:     LIGHTRIG_OTA"
  echo "Password: lightrig2024"
  echo ""
  echo "Arguments:"
  echo "  [interface]  WiFi interface to use (default: wlan0)"
  echo "               Find yours with: ip link show"
  echo ""
  echo "Flags:"
  echo "  -h  Show this help message"
  exit 0
fi

IFACE="${1:-wlan0}"
SSID="LIGHTRIG_OTA"
PASSWORD="lightrig2024"

echo "Starting hotspot on $IFACE..."
echo "SSID:     $SSID"
echo "Password: $PASSWORD"
echo ""

nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWORD"
